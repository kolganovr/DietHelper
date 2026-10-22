// Главная: панель ввода над экранной клавиатурой, состояние загрузки, примеры, очистка истории
(() => {
    const panel = document.getElementById('product-check');
    const input = document.getElementById('product-input');
    const form = document.getElementById('check-form');
    const button = document.getElementById('check-button');
    if (!panel || !input || !form) return;

    // iOS не уменьшает innerHeight при открытой клавиатуре, только visualViewport.
    // Android поднимает fixed-панель сам, там разница ~0.
    const adjustPosition = () => {
        if (document.activeElement !== input || !window.visualViewport) {
            panel.style.bottom = '0';
            return;
        }
        const keyboard = window.innerHeight - window.visualViewport.height;
        panel.style.bottom = keyboard > 50 ? `${keyboard}px` : '0';
    };

    input.addEventListener('focus', () => setTimeout(adjustPosition, 100));
    input.addEventListener('blur', () => { panel.style.bottom = '0'; });
    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', adjustPosition);
    }

    const setLoading = (loading) => {
        button.disabled = loading;
        button.textContent = loading ? 'Проверяю...' : 'Проверить';
        input.readOnly = loading;
        form.setAttribute('aria-busy', String(loading));
        const skeleton = document.getElementById('result-skeleton');
        const current = document.getElementById('current-result');
        if (skeleton) skeleton.hidden = !loading;
        if (current) current.hidden = loading;
    };

    form.addEventListener('submit', (event) => {
        if (form.getAttribute('aria-busy') === 'true') {
            event.preventDefault();
            return;
        }
        if (!input.value.trim()) {
            event.preventDefault();
            input.focus();
            return;
        }
        setLoading(true);
        input.blur();
        window.scrollTo({ top: 0 });
    });

    // Возврат кнопкой "Назад" из bfcache: снять состояние загрузки
    window.addEventListener('pageshow', (event) => {
        if (event.persisted) setLoading(false);
    });

    document.querySelectorAll('[data-example]').forEach((chip) => {
        chip.addEventListener('click', () => {
            input.value = chip.dataset.example;
            input.focus();
        });
    });

    const clearForm = document.getElementById('clear-history-form');
    if (clearForm) {
        clearForm.addEventListener('submit', (event) => {
            if (!confirm('Удалить всю историю проверок?')) event.preventDefault();
        });
    }
})();
