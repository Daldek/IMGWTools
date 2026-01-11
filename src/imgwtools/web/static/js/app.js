/**
 * IMGWTools - Main JavaScript file
 */

// HTMX configuration
document.body.addEventListener('htmx:configRequest', function(event) {
    // Add any custom headers if needed
    // event.detail.headers['X-Custom-Header'] = 'value';
});

// Handle HTMX errors
document.body.addEventListener('htmx:responseError', function(event) {
    console.error('HTMX request failed:', event.detail);
    const target = event.detail.target;
    if (target) {
        target.innerHTML = `
            <article class="error">
                <header>Błąd połączenia</header>
                <p>Nie udało się połączyć z serwerem. Spróbuj ponownie później.</p>
            </article>
        `;
    }
});

// Handle HTMX timeout
document.body.addEventListener('htmx:timeout', function(event) {
    console.error('HTMX request timeout:', event.detail);
    const target = event.detail.target;
    if (target) {
        target.innerHTML = `
            <article class="error">
                <header>Przekroczono czas oczekiwania</header>
                <p>Żądanie trwało zbyt długo. Spróbuj ponownie.</p>
            </article>
        `;
    }
});

// Form validation helpers
function validateYearRange(startInput, endInput) {
    const startYear = parseInt(startInput.value);
    const endYear = parseInt(endInput.value);

    if (startYear > endYear) {
        endInput.setCustomValidity('Rok końcowy musi być większy lub równy rokowi początkowemu');
        return false;
    }

    endInput.setCustomValidity('');
    return true;
}

// Setup year range validation on all forms
document.addEventListener('DOMContentLoaded', function() {
    const startYearInputs = document.querySelectorAll('input[name="start_year"]');
    const endYearInputs = document.querySelectorAll('input[name="end_year"]');

    startYearInputs.forEach((startInput, index) => {
        const endInput = endYearInputs[index];
        if (startInput && endInput) {
            startInput.addEventListener('change', () => validateYearRange(startInput, endInput));
            endInput.addEventListener('change', () => validateYearRange(startInput, endInput));
        }
    });
});

// Utility: Copy text to clipboard
function copyToClipboard(text, successMessage) {
    navigator.clipboard.writeText(text).then(() => {
        if (successMessage) {
            showNotification(successMessage, 'success');
        }
    }).catch(err => {
        console.error('Failed to copy:', err);
        showNotification('Nie udało się skopiować do schowka', 'error');
    });
}

// Utility: Show notification (simple alert for now)
function showNotification(message, type = 'info') {
    // Could be replaced with a toast notification library
    alert(message);
}

// Utility: Download text as file
function downloadAsFile(content, filename, mimeType = 'text/plain') {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// Utility: Format date for display
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('pl-PL', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Utility: Debounce function
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Keyboard shortcuts
document.addEventListener('keydown', function(event) {
    // Ctrl/Cmd + K to focus search
    if ((event.ctrlKey || event.metaKey) && event.key === 'k') {
        event.preventDefault();
        const searchInput = document.querySelector('input[type="search"], input#station-search');
        if (searchInput) {
            searchInput.focus();
        }
    }
});

// Log app initialization
console.log('IMGWTools v1.0.0 initialized');
