ymaps.ready(init);
let map, route, smoothRoute;
let placemarks = [];
let startPoint = null, endPoint = null, currentMode = 'point';
const placemarkIds = new Map(); // Хранилище ID меток
let trajectoryMode = 'manual';
let uploadedRoute = null;

let isPlaying = false;
let uavIcon;
let routePoints = [];

let uavPlacemark;

let altitudeChart;
let chartData = {
    distances: [], // Пройденное расстояние (км) по X
    altitudes: []  // Высота (м) по Y
};

let animationSpeed = 0.01; // Коэффициент скорости (можно регулировать)
let animationFrameId = null;
let animationStartTime = null;
let animationProgress = 0;

let hoveredPoint = null;
let hoverMarker = null;

let isRouteCalculated = false;

// Настройки иконок для точек маршрута
const pointIcons = {
    start: {
        preset: 'islands#greenDotIcon',
        iconColor: '#4CAF50'
    },
    end: {
        preset: 'islands#redDotIcon',
        iconColor: '#F44336'
    },
    point: {
        preset: 'islands#blueDotIcon',
        iconColor: '#316dff'
    }
};

window.removePlacemark = function(id) {
    const placemark = placemarkIds.get(id);
    if (!placemark) return;

    // Удаляем из специальных точек
    if (placemark === startPoint) startPoint = null;
    if (placemark === endPoint) endPoint = null;

    // Удаляем с карты и из хранилищ
    map.geoObjects.remove(placemark);
    placemarkIds.delete(id);
    placemarks = placemarks.filter(p => p !== placemark);

    updateRoute();

    // Удаляем сглаженный маршрут
    if (smoothRoute) {
        map.geoObjects.remove(smoothRoute);
        smoothRoute = null;
    }
};

function init() {
    document.body.style.overflow = 'hidden';
    try {
        // 1. Инициализация карты
        initMap();

        // 2. Инициализация UI элементов
        initUIElements();

        // 3. Инициализация обработчиков событий
        initEventHandlers();

        initTabs();

        document.getElementById('chart-toggle').addEventListener('click', toggleChartVisibility);

        console.log('Приложение успешно инициализировано');
    } catch (error) {
        console.error('Ошибка инициализации:', error);
        alert('Произошла ошибка при загрузке приложения. Пожалуйста, обновите страницу.');
    }

    // Обработчик кнопки анимации
    document.getElementById('animation-control').addEventListener('click', toggleAnimation);
}

function initMap() {

    // Функция для удаления нежелательных элементов
    function removeYandexButtons() {
        // Удаляем блок с кнопками
        const copyrightsPane = document.querySelector('.ymaps-2-1-79-copyrights-pane');
        if (copyrightsPane) copyrightsPane.remove();

        // Удаляем элементы такси
        const taxiElements = document.querySelectorAll('.ymaps-2-1-79-islets_taxi-label, .ymaps-2-1-79-islets_taxi-icon');
        taxiElements.forEach(el => el.remove());

        // Удаляем другие возможные элементы
        const promoElements = document.querySelectorAll('.ymaps-2-1-79-map-copyrights-promo, .ymaps-2-1-79-copyright__content');
        promoElements.forEach(el => el.remove());
    }

    // Создаем карту
    map = new ymaps.Map('map', {
        center: [54.6294, 39.7417],
        zoom: 11,
        controls: ['zoomControl']
    });

    removeYandexButtons();
    setTimeout(removeYandexButtons, 1000);
    setTimeout(removeYandexButtons, 3000);

    uavIcon = document.getElementById('uav-icon');
    if (!uavIcon) {
        uavIcon = document.createElement('img');
        uavIcon.id = 'uav-icon';
        uavIcon.src = 'drone_red.png';
        document.getElementById('map').appendChild(uavIcon);
    }

    // Проверка загрузки изображения
    uavIcon.onload = () => console.log('Иконка БПЛА загружена');
    uavIcon.onerror = () => {
        console.error('Ошибка загрузки иконки БПЛА');
        uavIcon.style.backgroundColor = 'red';
        uavIcon.style.borderRadius = '50%';
        uavIcon.style.border = '2px solid white';
    };
    const style = document.createElement('style');
    style.textContent = `
        .ymaps-2-1-79-searchbox,
        .ymaps-2-1-79-traffic-control,
        .ymaps-2-1-79-controls__toolbar_right {
            display: none !important;
        }
    `;
    document.head.appendChild(style);

    // Создаем основную линию маршрута
    route = new ymaps.Polyline([], {}, {
        strokeColor: "#0000FF",
        strokeWidth: 4,
        strokeOpacity: 0.7
    });
    map.geoObjects.add(route);

    // Создаем метку для БПЛА
    uavPlacemark = new ymaps.Placemark([0, 0], {}, {
        iconLayout: 'default#image',
        iconImageHref: 'data:image/svg+xml;utf8,' + encodeURIComponent(
            '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40">' +
            '<circle cx="20" cy="20" r="15" fill="red"/>' +
            '</svg>'
        ),
        iconImageSize: [20, 20],
        iconImageOffset: [-10, -10],
        zIndex: 999
    });

    // Добавляем метку на карту (но пока скрытую)
    map.geoObjects.add(uavPlacemark);
    uavPlacemark.options.set('visible', false);

    // Создаем маркер для выделения точки при наведении
    hoverMarker = new ymaps.Placemark([0, 0], {}, {
        iconLayout: 'default#image',
        iconImageHref: 'data:image/svg+xml;utf8,' + encodeURIComponent(
            '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">' +
            '<circle cx="12" cy="12" r="10" fill="yellow" stroke="black" stroke-width="2"/>' +
            '</svg>'
        ),
        iconImageSize: [24, 24],
        iconImageOffset: [-12, -12],
        zIndex: 1000
    });
    map.geoObjects.add(hoverMarker);
    hoverMarker.options.set('visible', false);

    // Обработчик движения мыши по карте
    map.events.add('mousemove', handleMapMouseMove);
    map.events.add('mouseout', handleMapMouseOut);
}

function initUIElements() {
    // Проверяем существование всех необходимых элементов
    const requiredElements = [
        'start-btn', 'end-btn', 'point-btn',
        'calculate', 'export', 'clear',
        'file-upload-container', 'file-info',
        'trajectory-file', 'select-trajectory-file',
        'camera-info', 'camera-params'  // Добавляем новые элементы
    ];

    requiredElements.forEach(id => {
        if (!document.getElementById(id)) {
            console.error(`Элемент с ID "${id}" не найден`);
        }
    });
}

function initEventHandlers() {
    // Обработчик клика по карте
    map.events.add('click', function(e) {
        const activeTab = document.querySelector('.tab-content.active').id;
        if (activeTab === 'manual-tab') {
            addWaypoint(e.get('coords'));
        }
    });

    // Инициализация кнопок управления
    initButton('#start-btn', () => setMode('start'));
    initButton('#end-btn', () => setMode('end'));
    initButton('#point-btn', () => setMode('point'));
    initButton('#calculate', function() {
        calculateRoute().then(() => {
            // После успешного построения маршрута активируем обработку наведения
            isRouteCalculated = true;
        });
    });
    initButton('#export', exportToGPX);
    initButton('#clear', clearAll);

    // Инициализация кнопок переключения карты
    document.querySelectorAll('.map-type').forEach(btn => {
        btn.addEventListener('click', function() {
            const type = this.dataset.type;
            document.querySelectorAll('.map-type').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            map.setType(type);
        });
    });

    // Инициализация переключателей режима траектории
    document.querySelectorAll('input[name="trajectoryMode"]').forEach(radio => {
        radio.addEventListener('change', function() {
            trajectoryMode = this.value;
            updateUIForTrajectoryMode();
        });
    });

    // Инициализация загрузки файлов
    const fileInput = document.getElementById('trajectory-file');
    const selectFileBtn = document.getElementById('select-trajectory-file');
    const fileInfo = document.getElementById('file-info');

    if (selectFileBtn && fileInput) {
        selectFileBtn.addEventListener('click', () => fileInput.click());

        fileInput.addEventListener('change', function(e) {
            if (e.target.files.length > 0) {
                const file = e.target.files[0];
                if (fileInfo) fileInfo.textContent = `Выбран файл: ${file.name}`;

                if (file.name.endsWith('.srt')) {
                    parseSRTFile(file);
                } else if (file.name.endsWith('.SRT')) {
                    parseSRTFile(file);
                } else {
                    alert('Поддерживаются только файлы .srt');
                }
            }
        });
    }
}

// Вспомогательная функция для инициализации кнопок
function initButton(selector, handler) {
    const button = document.querySelector(selector);
    if (button) {
        button.addEventListener('click', handler);
    } else {
        console.error(`Кнопка не найдена: ${selector}`);
    }
}

// Инициализация вкладок
function initTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    tabBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            // Скрываем все вкладки
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });

            // Убираем активное состояние у всех кнопок
            document.querySelectorAll('.tab-btn').forEach(btn => {
                btn.classList.remove('active');
                btn.style.opacity = '0.8';
            });

            // Активируем текущую вкладку
            const tabId = this.getAttribute('data-tab');
            document.getElementById(tabId).classList.add('active');
            this.classList.add('active');
            this.style.opacity = '1';

            // Очищаем карту при переключении
            clearAll();
        });
    });
}

// Функция инициализации графика
function initAltitudeChart() {
    const ctx = document.getElementById("altitude-chart").getContext("2d");
    altitudeChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: chartData.distances.map(d => d.toFixed(2)),
            datasets: [{
                label: "Высота",
                data: chartData.altitudes,
                borderColor: "#0000FF",
                backgroundColor: "rgba(0,0,255,0.21)",
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 0 // Убираем точки на основной линии
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `Высота: ${context.parsed.y.toFixed(2)} м`;
                        },
                        afterLabel: function(context) {
                            return `Расстояние: ${chartData.distances[context.dataIndex].toFixed(2)} км`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    display: false
                },
                y: {
                    display: true
                }
            }
        }
    });
}

function toggleChartVisibility() {
    const chartContainer = document.getElementById('chart-container');
    const toggleBtn = document.getElementById('chart-toggle');

    if (chartContainer.style.display === 'none' || !chartContainer.style.display) {
        chartContainer.style.display = 'block';
        toggleBtn.textContent = '📉';
        // Инициализируем график если он еще не создан
        if (!altitudeChart && chartData.distances.length > 0) {
            initAltitudeChart();
        }
    } else {
        chartContainer.style.display = 'none';
        toggleBtn.textContent = '📈';
    }

    // Обновляем высоту карты
    updateMapHeight();
}

function updateMapHeight() {
    const chartContainer = document.getElementById('chart-container');
    const mapElement = document.getElementById('map');

    if (chartContainer.style.display === 'block') {
        mapElement.classList.add('with-chart');
    } else {
        mapElement.classList.remove('with-chart');
    }
}

// Обработчик движения мыши по карте
function handleMapMouseMove(e) {
   if (routePoints.length === 0 && !isRouteCalculated) return;

    const mouseCoords = e.get('coords');
    let closestPoint = null;
    let minDistance = Infinity;

    // Обработка маршрута из файла
    if (routePoints.length > 0) {
        // Оптимизированный поиск - проверяем каждую 5-ю точку сначала
        for (let i = 0; i < routePoints.length; i += 5) {
            const point = routePoints[i];
            const distance = calculatePixelDistance(map, mouseCoords, [point.lat, point.lng]);

            if (distance < minDistance) {
                minDistance = distance;
                closestPoint = {
                    ...point,
                    index: i
                };
            }
        }

        // Проверяем соседние точки для точности
        const startIdx = Math.max(0, (closestPoint?.index || 0) - 10);
        const endIdx = Math.min(routePoints.length - 1, (closestPoint?.index || 0) + 10);

        for (let i = startIdx; i <= endIdx; i++) {
            const point = routePoints[i];
            const distance = calculatePixelDistance(map, mouseCoords, [point.lat, point.lng]);

            if (distance < minDistance) {
                minDistance = distance;
                closestPoint = {
                    ...point,
                    index: i
                };
            }
        }
    }
    // Обработка сглаженного маршрута (старая логика)
    else if (smoothRoute) {
        const coordinates = smoothRoute.geometry.getCoordinates();

        for (let i = 0; i < coordinates.length; i++) {
            const coord = coordinates[i];
            const distance = calculatePixelDistance(map, mouseCoords, coord);

            if (distance < minDistance) {
                minDistance = distance;
                closestPoint = {
                    lat: coord[0],
                    lng: coord[1],
                    alt: 100,
                    index: i
                };
            }
        }

        for (let i = 0; i < coordinates.length - 1; i++) {
            const start = coordinates[i];
            const end = coordinates[i+1];
            const closestOnSegment = findClosestPointOnSegment(mouseCoords, start, end);
            const distance = calculatePixelDistance(map, mouseCoords, closestOnSegment);

            if (distance < minDistance) {
                minDistance = distance;
                closestPoint = {
                    lat: closestOnSegment[0],
                    lng: closestOnSegment[1],
                    alt: 100,
                    index: i
                };
            }
        }
    }
    // Обработка резкого маршрута (ручной режим, старая логика)
    else if (route && isRouteCalculated) {
        const coordinates = route.geometry.getCoordinates();

        for (let i = 0; i < coordinates.length; i++) {
            const coord = coordinates[i];
            const distance = calculatePixelDistance(map, mouseCoords, coord);

            if (distance < minDistance) {
                minDistance = distance;
                closestPoint = {
                    lat: coord[0],
                    lng: coord[1],
                    alt: 100,
                    index: i
                };
            }
        }

        for (let i = 0; i < coordinates.length - 1; i++) {
            const start = coordinates[i];
            const end = coordinates[i+1];

            for (let j = 0; j <= 10; j++) {
                const t = j / 10;
                const interpolated = [
                    start[0] + (end[0] - start[0]) * t,
                    start[1] + (end[1] - start[1]) * t
                ];
                const distance = calculatePixelDistance(map, mouseCoords, interpolated);

                if (distance < minDistance) {
                    minDistance = distance;
                    closestPoint = {
                        lat: interpolated[0],
                        lng: interpolated[1],
                        alt: 100,
                        index: i
                    };
                }
            }
        }
    }

    // Обновляем маркер
    if (closestPoint && minDistance < 15) {
        hoveredPoint = closestPoint;
        updateHoverMarker();
        showHoveredPointInfo();
    } else {
        clearHoverMarker();
    }
}

// Упрощенная версия для файлового маршрута
function findClosestPointOptimized(mouseCoords, coordsArray, pointsArray) {
    let closestIndex = 0;
    let minDist = Infinity;

    // Линейный поиск с шагом 5 точек для оптимизации
    for (let i = 0; i < coordsArray.length; i += 5) {
        const dist = calculatePixelDistance(map, mouseCoords, coordsArray[i]);
        if (dist < minDist) {
            minDist = dist;
            closestIndex = i;
        }
    }

    // Проверяем соседние точки для точности
    const start = Math.max(0, closestIndex - 10);
    const end = Math.min(coordsArray.length - 1, closestIndex + 10);

    for (let i = start; i <= end; i++) {
        const dist = calculatePixelDistance(map, mouseCoords, coordsArray[i]);
        if (dist < minDist) {
            minDist = dist;
            closestIndex = i;
        }
    }

    return {
        ...pointsArray[closestIndex],
        index: closestIndex
    };
}

// Вспомогательная функция для нахождения ближайшей точки на отрезке
function findClosestPointOnSegment(point, lineStart, lineEnd) {
    const projection = map.options.get('projection');
    const zoom = map.getZoom();

    const pointPx = map.converter.globalToPage(projection.toGlobalPixels(point, zoom));
    const startPx = map.converter.globalToPage(projection.toGlobalPixels(lineStart, zoom));
    const endPx = map.converter.globalToPage(projection.toGlobalPixels(lineEnd, zoom));

    const lineVec = [endPx[0] - startPx[0], endPx[1] - startPx[1]];
    const pointVec = [pointPx[0] - startPx[0], pointPx[1] - startPx[1]];

    const lineLengthSq = lineVec[0] * lineVec[0] + lineVec[1] * lineVec[1];

    let t = 0;
    if (lineLengthSq !== 0) {
        t = (pointVec[0] * lineVec[0] + pointVec[1] * lineVec[1]) / lineLengthSq;
        t = Math.max(0, Math.min(1, t));
    }

    const closestPx = [
        startPx[0] + t * lineVec[0],
        startPx[1] + t * lineVec[1]
    ];

    const globalPx = map.converter.pageToGlobal(closestPx);
    return projection.fromGlobalPixels(globalPx, zoom);
}

// Вспомогательная функция для расчета коэффициента интерполяции
function calculateInterpolationFactor(start, end, point) {
    const dx = end[0] - start[0];
    const dy = end[1] - start[1];

    if (Math.abs(dx) > Math.abs(dy)) {
        return (point[0] - start[0]) / dx;
    } else {
        return (point[1] - start[1]) / dy;
    }
}

function calculatePixelDistance(map, coord1, coord2) {
    const projection = map.options.get('projection');
    const pixel1 = map.converter.globalToPage(projection.toGlobalPixels(coord1, map.getZoom()));
    const pixel2 = map.converter.globalToPage(projection.toGlobalPixels(coord2, map.getZoom()));

    const dx = pixel1[0] - pixel2[0];
    const dy = pixel1[1] - pixel2[1];

    return Math.sqrt(dx * dx + dy * dy);
}

// Обработчик выхода мыши за пределы карты
function handleMapMouseOut() {
    clearHoverMarker();
}

// Обновление маркера при наведении
function updateHoverMarker() {
    if (!hoveredPoint || !hoverMarker) return;

    hoverMarker.geometry.setCoordinates([hoveredPoint.lat, hoveredPoint.lng]);
    hoverMarker.options.set('visible', true);
}

// Очистка маркера при наведении
function clearHoverMarker() {
    if (!hoverMarker) return;

    hoverMarker.options.set('visible', false);
    hoveredPoint = null;

    // Очищаем информацию о точке
    const hoverInfo = document.getElementById('hover-info');
    if (hoverInfo) {
        hoverInfo.style.display = 'none';
    }
}

// Отображение информации о точке
function showHoveredPointInfo() {
    const hoverInfo = document.getElementById('hover-info');
    if (!hoverInfo) return;

    if (hoveredPoint) {
        let infoHTML = `
            <div><strong>Координаты:</strong> ${hoveredPoint.lat.toFixed(6)}, ${hoveredPoint.lng.toFixed(6)}</div>
            <div><strong>Высота:</strong> ${hoveredPoint.alt?.toFixed(2) || 'N/A'} м</div>
        `;

        // Для маршрута из файла показываем индекс точки
        if (hoveredPoint.index !== undefined) {
            infoHTML += `<div><strong>Точка:</strong> ${hoveredPoint.index + 1} из ${routePoints.length}</div>`;
        }

        // Метаданные из SRT файла
        if (hoveredPoint.metadata) {
            const meta = hoveredPoint.metadata;
            infoHTML += `<div><strong>Параметры съемки:</strong></div>`;
            if (meta.date) infoHTML += `<div>• Дата: ${meta.date}</div>`;
            if (meta.iso) infoHTML += `<div>• ISO: ${meta.iso}</div>`;
            if (meta.shutter) infoHTML += `<div>• Выдержка: ${meta.shutter}</div>`;
            if (meta.fnum) infoHTML += `<div>• Диафрагма: f/${meta.fnum}</div>`;
            if (meta.focal_len) infoHTML += `<div>• Фокус: ${meta.focal_len} мм</div>`;
        }

        hoverInfo.innerHTML = infoHTML;
        hoverInfo.style.display = 'block';
    } else {
        hoverInfo.style.display = 'none';
    }
}

// Функция обновления данных графика
function updateChart(points) {
    if (!points || points.length === 0) {
        console.warn("Нет данных для построения графика");
        return;
    }

    // Очищаем предыдущие данные
    chartData.distances = [];
    chartData.altitudes = [];

    // Рассчитываем кумулятивное расстояние
    let totalDistance = 0;
    let prevPoint = null;

    points.forEach((point, index) => {
        if (prevPoint) {
            totalDistance += calculateDistance(
                prevPoint.lat, prevPoint.lng,
                point.lat, point.lng
            );
        }

        chartData.distances.push(totalDistance);
        chartData.altitudes.push(point.alt || 0);
        prevPoint = point;
    });

    // Показываем график
    const chartContainer = document.getElementById("chart-container");
    chartContainer.classList.add("visible");
    document.getElementById("chart-toggle").textContent = '📉';
    document.getElementById("map").classList.add('with-chart');

    // Инициализируем или обновляем график
    if (!altitudeChart) {
        initAltitudeChart();
    } else {
        altitudeChart.data.labels = chartData.distances.map(d => d.toFixed(2));
        altitudeChart.data.datasets[0].data = chartData.altitudes;
        altitudeChart.update();
    }
}

// Вспомогательная функция для расчета расстояния между точками
function calculateDistance(lat1, lon1, lat2, lon2) {
    const R = 6371; // Радиус Земли в км
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a =
        Math.sin(dLat/2) * Math.sin(dLat/2) +
        Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
        Math.sin(dLon/2) * Math.sin(dLon/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return R * c;
}

// Функция для обновления позиции маркера на графике
function updateChartMarker(index) {
    if (!altitudeChart || index >= chartData.distances.length) return;

    // Создаем новый dataset для маркера, если его нет
    if (altitudeChart.data.datasets.length === 1) {
        altitudeChart.data.datasets.push({
            data: [],
            pointBackgroundColor: 'red',
            pointBorderColor: 'white',
            pointRadius: 6,
            pointHoverRadius: 8,
            showLine: false
        });
    }

    // Обновляем данные маркера
    const markerData = Array(chartData.distances.length).fill(null);
    markerData[index] = chartData.altitudes[index];
    altitudeChart.data.datasets[1].data = markerData;

    // Обновляем график без анимации
    altitudeChart.update('none');
}

// Функция для обновления интерфейса в зависимости от режима
function updateUIForTrajectoryMode() {
    const fileUploadContainer = document.getElementById('file-upload-container');
    const pointTypeButtons = document.querySelector('.point-type-buttons');
    const calculateBtn = document.getElementById('calculate');

    if (!fileUploadContainer || !pointTypeButtons || !calculateBtn) {
        console.error('Не найдены элементы интерфейса для обновления');
        return;
    }

    if (trajectoryMode === 'file') {
        fileUploadContainer.style.display = 'block';
        pointTypeButtons.style.opacity = '0.5';
        pointTypeButtons.style.pointerEvents = 'none';
        calculateBtn.style.opacity = '0.5';
        calculateBtn.style.pointerEvents = 'none';
        clearAll(); // Очищаем все точки при переключении в режим файла
    } else {
        fileUploadContainer.style.display = 'none';
        pointTypeButtons.style.opacity = '1';
        pointTypeButtons.style.pointerEvents = 'auto';
        calculateBtn.style.opacity = '1';
        calculateBtn.style.pointerEvents = 'auto';
        if (uploadedRoute) {
            map.geoObjects.remove(uploadedRoute);
            uploadedRoute = null;
        }
        // Останавливаем анимацию при переключении режима
        if (isPlaying) {
            toggleAnimation();
        }
    }
}

async function parseSRTFile(file) {
    if (isPlaying) {
        toggleAnimation();
    }
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('http://localhost:8000/api/import-srt', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        if (data.status !== 'success') {
            throw new Error('Ошибка сервера');
        }

        // Сохраняем точки для анимации
        routePoints = data.points;

        // Отображаем маршрут
        displayRoute(routePoints);

        // Обновляем график
        updateChart(routePoints);

        // Показываем параметры первой точки
        if (routePoints.length > 0) {
            showCameraParams(routePoints[0]);
        }

        if (uploadedRoute) {
            map.geoObjects.remove(uploadedRoute);
        }

        const coords = data.points.map(p => [p.lat, p.lng]);
        uploadedRoute = new ymaps.Polyline(coords, {}, {
            strokeColor: "#0000FF",
            strokeWidth: 4,
            strokeOpacity: 0.9
        });

        map.geoObjects.add(uploadedRoute);
        map.setBounds(uploadedRoute.geometry.getBounds());

    } catch (err) {
        console.error('Ошибка загрузки SRT:', err);
        alert('Ошибка при загрузке файла: ' + err.message);
    }
}

// Функция отображения маршрута
function displayRoute(points) {
    if (uploadedRoute) {
        map.geoObjects.remove(uploadedRoute);
    }

    const coords = points.map(p => [p.lat, p.lng]);
    uploadedRoute = new ymaps.Polyline(coords, {}, {
        strokeColor: "#0000FF",
        strokeWidth: 4,
        strokeOpacity: 0.9
    });

    map.geoObjects.add(uploadedRoute);
    map.setBounds(uploadedRoute.geometry.getBounds());
}

function toggleAnimation() {
    const animBtn = document.getElementById('animation-control');
    if (isPlaying) {
        // Останавливаем анимацию
        cancelAnimationFrame(animationFrameId);
        animationFrameId = null;
        isPlaying = false;
        animBtn.textContent = 'Старт анимации';
        animBtn.classList.remove('playing');
        uavPlacemark.options.set('visible', false);
    } else {
        // Запускаем анимацию
        if (routePoints.length === 0) {
            alert('Сначала загрузите файл траектории');
            return;
        }

        animBtn.textContent = 'Стоп анимации';
        animBtn.classList.add('playing');
        isPlaying = true;
        animationStartTime = null;
        animationProgress = 0;
        uavPlacemark.options.set('visible', true);
        startAnimation();
    }
}

// Запуск анимации
function startAnimation() {
    if (!uavIcon) return;
    animationFrameId = requestAnimationFrame(animateUAV);
}

function animateUAV(timestamp) {
    if (!animationStartTime) animationStartTime = timestamp;
    const elapsed = timestamp - animationStartTime;
    animationProgress = Math.min(elapsed / (2000 / animationSpeed), 1);

    const currentPosition = getPositionOnRoute(animationProgress);
    if (!currentPosition) {
        stopAnimation();
        return;
    }

    updateUAVPosition(currentPosition);
    updateChartMarker(currentPosition.index); // Обновляем маркер на графике

    if (animationProgress < 1) {
        animationFrameId = requestAnimationFrame(animateUAV);
    } else {
        stopAnimation();
    }
}

function stopAnimation() {
    if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
        animationFrameId = null;
    }
    isPlaying = false;

    const animBtn = document.getElementById('animation-control');
    if (animBtn) {
        animBtn.textContent = 'Старт анимации';
        animBtn.classList.remove('playing');
    }

    // Скрываем метку БПЛА при остановке
    if (uavPlacemark) {
        uavPlacemark.options.set('visible', false);
    }
}

function getPositionOnRoute(progress) {
    if (!routePoints || routePoints.length === 0) return null;

    // Вычисляем точное положение на маршруте
    const totalPoints = routePoints.length;
    const exactIndex = progress * (totalPoints - 1);
    const index = Math.floor(exactIndex);
    const fraction = exactIndex - index;

    // Если это последняя точка
    if (index >= totalPoints - 1) {
        return {
            ...routePoints[totalPoints - 1],
            index: totalPoints - 1
        };
    }

    // Интерполируем между точками
    const p1 = routePoints[index];
    const p2 = routePoints[index + 1];

    return {
        lat: p1.lat + (p2.lat - p1.lat) * fraction,
        lng: p1.lng + (p2.lng - p1.lng) * fraction,
        alt: p1.alt + (p2.alt - p1.alt) * fraction,
        index: index
    };
}

// Обновление позиции БПЛА
function updateUAVPosition(position) {
    if (!position || !position.lat || !position.lng || !uavPlacemark) {
        console.error('Некорректные параметры позиции:', position);
        return;
    }

    try {
        // Обновляем координаты метки
        uavPlacemark.geometry.setCoordinates([position.lat, position.lng]);

        // Обновляем информацию о камере
        if (position.alt !== undefined) {
            showCameraParams({
                lat: position.lat,
                lng: position.lng,
                alt: position.alt
            });
        }
    } catch (error) {
        console.error('Ошибка при обновлении позиции БПЛА:', error);
        throw error; // Пробрасываем ошибку выше для обработки в animateUAV
    }
}

// Функция для отображения параметров съемки
function showCameraParams(params) {
    const container = document.getElementById('camera-params');
    const cameraInfo = document.getElementById('camera-info');

    // Проверяем существование элементов
    if (!container || !cameraInfo) {
        console.error('Не найдены элементы для отображения параметров камеры');
        return;
    }

    // Проверяем наличие параметров
    if (!params) {
        console.error('Не переданы параметры камеры');
        return;
    }

    try {
        container.innerHTML = `
            <div><strong>Координаты:</strong> ${params.lat?.toFixed(6) || 'N/A'}, ${params.lng?.toFixed(6) || 'N/A'}</div>
            <div><strong>Высота:</strong> ${params.alt?.toFixed(2) || 'N/A'} м</div>
        `;
        cameraInfo.style.display = 'block';
    } catch (error) {
        console.error('Ошибка при отображении параметров камеры:', error);
    }
}

function setMode(mode) {
    currentMode = mode;
    const startBtn = document.getElementById('start-btn');
    const endBtn = document.getElementById('end-btn');
    const pointBtn = document.getElementById('point-btn');

    if (startBtn && endBtn && pointBtn) {
        startBtn.classList.remove('active');
        endBtn.classList.remove('active');
        pointBtn.classList.remove('active');
        document.getElementById(mode + '-btn').classList.add('active');
    }
}

function addWaypoint(coords) {
    if (trajectoryMode === 'file') return;

    // Удаляем предыдущую точку, если это начальная или конечная
    if (currentMode === 'start' && startPoint) {
        removePlacemark(startPoint.properties.get('id'));
    } else if (currentMode === 'end' && endPoint) {
        removePlacemark(endPoint.properties.get('id'));
    }

    // Создаем уникальный ID для метки
    const placemarkId = 'pm_' + Date.now() + '_' + Math.floor(Math.random() * 1000);

    // Создаем метку
    const placemark = new ymaps.Placemark(coords, {
        balloonContentHeader: `${getTypeName(currentMode)}<br>точка`,
        balloonContentBody: `
            <div>Широта: ${coords[0].toFixed(6)}</div>
            <div>Долгота: ${coords[1].toFixed(6)}</div>
            <div class="balloon-footer">
                <button class="delete-btn" id="delete-${placemarkId}">Удалить</button>
            </div>
        `
    }, {
        preset: pointIcons[currentMode].preset,
        iconColor: pointIcons[currentMode].iconColor,
        draggable: true,
        balloonCloseButton: true, // Добавляем эту строку для включения стандартного крестика
        balloonPanelMaxMapArea: 0, // Отключаем автоматический расчет размера
        balloonMaxWidth: 200,      // Максимальная ширина балуна в пикселях
        balloonMinWidth: 150       // Минимальная ширина балуна
    });

    // Сохраняем ID и тип точки
    placemark.properties.set('id', placemarkId);
    placemark.properties.set('type', currentMode);
    placemarkIds.set(placemarkId, placemark);

    // Добавляем метку на карту
    map.geoObjects.add(placemark);

    // Обработчик открытия балуна
    placemark.events.add('balloonopen', function() {
        // Ждем пока балун полностью отрендерится
        setTimeout(() => {
            // Находим кнопку удаления по ID
            const deleteBtn = document.getElementById(`delete-${placemarkId}`);
            if (deleteBtn) {
                deleteBtn.onclick = (e) => {
                    e.stopPropagation();
                    removePlacemark(placemarkId);
                };
            }
        }, 50);
    });

    // Обработчик перемещения точки
    placemark.events.add('dragend', function() {
        updateRoute();
        if (smoothRoute) {
            map.geoObjects.remove(smoothRoute);
            smoothRoute = null;
        }
    });

    // Сохраняем точку
    if (currentMode === 'start') startPoint = placemark;
    if (currentMode === 'end') endPoint = placemark;
    placemarks.push(placemark);

    updateRoute();
}

function getTypeName(type) {
    const names = {
        'start': 'Начальная',
        'end': 'Конечная',
        'point': 'Промежуточная'
    };
    return names[type];
}

function updateRoute() {
    // Сортируем точки: начальная -> промежуточные -> конечная
    const coordinates = [];
    if (startPoint) coordinates.push(startPoint.geometry.getCoordinates());
    coordinates.push(...placemarks
        .filter(p => p !== startPoint && p !== endPoint)
        .map(p => p.geometry.getCoordinates()));
    if (endPoint) coordinates.push(endPoint.geometry.getCoordinates());

    route.geometry.setCoordinates(coordinates);
}

function clearAll() {
    // Очищаем все точки маршрута
    placemarks.forEach(pm => map.geoObjects.remove(pm));
    placemarks = [];
    startPoint = null;
    endPoint = null;

    // Удаляем маршруты
    if (smoothRoute) map.geoObjects.remove(smoothRoute);
    if (uploadedRoute) map.geoObjects.remove(uploadedRoute);
    smoothRoute = null;
    uploadedRoute = null;

    // Сбрасываем флаг
    isRouteCalculated = false;

    // Очищаем данные файла
    routePoints = [];
    const fileInput = document.getElementById('trajectory-file');
    if (fileInput) fileInput.value = '';

    const fileInfo = document.getElementById('file-info');
    if (fileInfo) fileInfo.textContent = '';

    // Останавливаем анимацию
    if (isPlaying) toggleAnimation();

    // Обновляем маршрут
    updateRoute();

    if (altitudeChart) {
        altitudeChart.destroy();
        altitudeChart = null;
    }

    // Убедитесь, что график скрыт
    document.getElementById('chart-container').classList.remove('show');
    document.getElementById('chart-toggle').textContent = '📈';
    updateMapHeight();
    clearHoverMarker();
}

async function calculateRoute() {
    if (placemarks.length < 2) {
        alert('Добавьте минимум 2 точки');
        return;
    }

    if (!startPoint) {
        alert('Не указана начальная точка');
        return;
    }

    if (!endPoint) {
        alert('Не указана конечная точка');
        return;
    }

    try {
        const routeType = document.querySelector('input[name="routeType"]:checked').value;
        const smooth = routeType === 'smooth';

        const points = [];
        if (startPoint) points.push(getPointData(startPoint));
        points.push(...placemarks
            .filter(p => p !== startPoint && p !== endPoint)
            .map(p => getPointData(p)));
        if (endPoint) points.push(getPointData(endPoint));

        const response = await fetch('http://localhost:8000/api/calculate-route', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                points: points,
                smooth: smooth
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        if (data.status !== 'success') {
            throw new Error('Ошибка сервера');
        }

        if (smoothRoute) {
            map.geoObjects.remove(smoothRoute);
        }

        const smoothCoords = data.points.map(p => [p.lat, p.lng]);

        smoothRoute = new ymaps.Polyline(smoothCoords, {}, {
            strokeColor: "#c800ff",
            strokeWidth: 4,
            strokeOpacity: 0.9
        });

        map.geoObjects.add(smoothRoute);

        // Обновляем основной маршрут для резкой траектории
        if (!smooth) {
            const routeCoords = [];
            if (startPoint) routeCoords.push(startPoint.geometry.getCoordinates());
            routeCoords.push(...placemarks
                .filter(p => p !== startPoint && p !== endPoint)
                .map(p => p.geometry.getCoordinates()));
            if (endPoint) routeCoords.push(endPoint.geometry.getCoordinates());

            route.geometry.setCoordinates(routeCoords);
        }

        // Устанавливаем флаг, что маршрут построен
        isRouteCalculated = true;

    } catch (err) {
        console.error('Ошибка расчета маршрута:', err);
        alert('Ошибка расчета маршрута: ' + err.message);
    }
}

function getPointData(placemark) {
    const coords = placemark.geometry.getCoordinates();
    return {
        lat: coords[0],
        lng: coords[1],
        type: placemark.properties.get('type') || 'point'
    };
}

async function exportToGPX() {
    if (placemarks.length < 2) {
        alert('Добавьте минимум 2 точки');
        return;
    }

    try {
        const points = [];
        if (startPoint) points.push(getPointData(startPoint));
        points.push(...placemarks
            .filter(p => p !== startPoint && p !== endPoint)
            .map(p => getPointData(p)));
        if (endPoint) points.push(getPointData(endPoint));

        const response = await fetch('http://localhost:8000/api/export-gpx', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                points: points,
                smooth: false
            })
        });

        const data = await response.json();

        const blob = new Blob([data.gpx], {type: 'application/xml'});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'маршрут_' + new Date().toISOString().slice(0, 10) + '.gpx';
        a.click();
    } catch (err) {
        alert('Ошибка экспорта: ' + err.message);
    }
}

window.removePlacemark = removePlacemark;