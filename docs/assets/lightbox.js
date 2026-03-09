// Lightbox met zoom en pan voor het uitvergroten van afbeeldingen
document.addEventListener('DOMContentLoaded', function() {
    // Maak overlay elementen
    var overlay = document.createElement('div');
    overlay.className = 'lightbox-overlay';
    var overlayImg = document.createElement('img');
    var hint = document.createElement('div');
    hint.className = 'lightbox-hint';
    hint.textContent = 'Scroll om te zoomen \u2022 Dubbelklik om in te zoomen \u2022 Klik ernaast om te sluiten';
    overlay.appendChild(overlayImg);
    overlay.appendChild(hint);
    document.body.appendChild(overlay);

    // Zoom & pan state
    var scale = 1;
    var translateX = 0;
    var translateY = 0;
    var isDragging = false;
    var dragStartX = 0;
    var dragStartY = 0;
    var lastTranslateX = 0;
    var lastTranslateY = 0;
    var minScale = 1;
    var maxScale = 20;

    function applyTransform() {
        overlayImg.style.transform = 'translate(' + translateX + 'px, ' + translateY + 'px) scale(' + scale + ')';
        overlayImg.style.cursor = scale > 1 ? 'grab' : 'zoom-in';
        hint.style.opacity = scale > 1 ? '0' : '';
    }

    function resetZoom() {
        scale = 1;
        translateX = 0;
        translateY = 0;
        applyTransform();
    }

    function closeLightbox() {
        overlay.classList.remove('active');
        resetZoom();
        isDragging = false;
    }

    // Scrollwiel om in/uit te zoomen (gecentreerd op muispositie)
    overlay.addEventListener('wheel', function(e) {
        e.preventDefault();
        var rect = overlayImg.getBoundingClientRect();
        var imgCenterX = rect.left + rect.width / 2;
        var imgCenterY = rect.top + rect.height / 2;

        // Muispositie relatief ten opzichte van het midden van de afbeelding
        var mouseX = e.clientX - imgCenterX;
        var mouseY = e.clientY - imgCenterY;

        var oldScale = scale;
        var delta = e.deltaY > 0 ? 0.85 : 1.18;
        scale = Math.min(maxScale, Math.max(minScale, scale * delta));

        // Pas translate aan zodat zoom gecentreerd is op muispositie
        var ratio = scale / oldScale;
        translateX = mouseX - ratio * (mouseX - translateX);
        translateY = mouseY - ratio * (mouseY - translateY);

        applyTransform();
    }, { passive: false });

    // Drag om te pannen (alleen als ingezoomd)
    overlayImg.addEventListener('mousedown', function(e) {
        if (scale <= 1) return;
        e.preventDefault();
        isDragging = true;
        dragStartX = e.clientX;
        dragStartY = e.clientY;
        lastTranslateX = translateX;
        lastTranslateY = translateY;
        overlayImg.style.cursor = 'grabbing';
    });

    document.addEventListener('mousemove', function(e) {
        if (!isDragging) return;
        translateX = lastTranslateX + (e.clientX - dragStartX);
        translateY = lastTranslateY + (e.clientY - dragStartY);
        applyTransform();
    });

    document.addEventListener('mouseup', function() {
        if (isDragging) {
            isDragging = false;
            overlayImg.style.cursor = scale > 1 ? 'grab' : 'zoom-out';
        }
    });

    // Touch-ondersteuning voor pinch-to-zoom en drag
    var lastTouchDist = 0;
    var lastTouchX = 0;
    var lastTouchY = 0;

    overlay.addEventListener('touchstart', function(e) {
        if (e.touches.length === 2) {
            e.preventDefault();
            var dx = e.touches[0].clientX - e.touches[1].clientX;
            var dy = e.touches[0].clientY - e.touches[1].clientY;
            lastTouchDist = Math.sqrt(dx * dx + dy * dy);
        } else if (e.touches.length === 1 && scale > 1) {
            isDragging = true;
            lastTouchX = e.touches[0].clientX;
            lastTouchY = e.touches[0].clientY;
            lastTranslateX = translateX;
            lastTranslateY = translateY;
        }
    }, { passive: false });

    overlay.addEventListener('touchmove', function(e) {
        if (e.touches.length === 2) {
            e.preventDefault();
            var dx = e.touches[0].clientX - e.touches[1].clientX;
            var dy = e.touches[0].clientY - e.touches[1].clientY;
            var dist = Math.sqrt(dx * dx + dy * dy);
            if (lastTouchDist > 0) {
                var ratio = dist / lastTouchDist;
                scale = Math.min(maxScale, Math.max(minScale, scale * ratio));
                applyTransform();
            }
            lastTouchDist = dist;
        } else if (e.touches.length === 1 && isDragging) {
            e.preventDefault();
            translateX = lastTranslateX + (e.touches[0].clientX - lastTouchX);
            translateY = lastTranslateY + (e.touches[0].clientY - lastTouchY);
            applyTransform();
        }
    }, { passive: false });

    overlay.addEventListener('touchend', function() {
        isDragging = false;
        lastTouchDist = 0;
    });

    // Klik op overlay achtergrond sluit lightbox (niet bij drag of zoom)
    var clickStartX = 0, clickStartY = 0;
    overlay.addEventListener('mousedown', function(e) {
        clickStartX = e.clientX;
        clickStartY = e.clientY;
    });
    overlay.addEventListener('click', function(e) {
        // Alleen sluiten als het geen drag was en als het op de achtergrond is
        var moved = Math.abs(e.clientX - clickStartX) + Math.abs(e.clientY - clickStartY);
        if (moved > 5) return;
        if (e.target === overlay) {
            closeLightbox();
        } else if (e.target === overlayImg && scale <= 1) {
            closeLightbox();
        }
    });

    // Dubbelklik op afbeelding om in/uit te zoomen
    overlayImg.addEventListener('dblclick', function(e) {
        e.stopPropagation();
        if (scale > 1) {
            resetZoom();
        } else {
            scale = 3;
            // Zoom naar de plek waar geklikt is
            var rect = overlayImg.getBoundingClientRect();
            var imgCenterX = rect.left + rect.width / 2;
            var imgCenterY = rect.top + rect.height / 2;
            translateX = (imgCenterX - e.clientX) * (scale - 1);
            translateY = (imgCenterY - e.clientY) * (scale - 1);
            applyTransform();
        }
    });

    // Escape sluit lightbox
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') closeLightbox();
    });

    // Voeg klik-handler toe aan alle content-afbeeldingen
    var content = document.querySelector('.wy-nav-content-wrap') || document.querySelector('[role="main"]') || document.body;
    content.addEventListener('click', function(e) {
        var img = e.target;
        if (img.tagName !== 'IMG') return;
        // Skip badges en iconen (kleiner dan 80px)
        if (img.naturalWidth < 80 && img.naturalHeight < 80) return;
        e.preventDefault();
        resetZoom();
        overlayImg.src = img.src;
        overlayImg.alt = img.alt;
        overlay.classList.add('active');
    });
});
