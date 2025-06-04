/**
 * DTF Design Packer - Main JavaScript
 * Contains utility functions and common interactions
 */

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    initTooltips();
    
    // Initialize animations
    initAnimations();
    
    // Add custom event listeners
    setupEventListeners();
    
    // Initialize toast system
    window.showToast = showToast;
    
    console.log('DTF Design Packer JS initialized');
});

/**
 * Initialize Bootstrap tooltips
 */
function initTooltips() {
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    if (tooltipTriggerList.length > 0) {
        [...tooltipTriggerList].map(tooltipTriggerEl => {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }
}

/**
 * Initialize scroll animations
 */
function initAnimations() {
    // Get all elements with animation classes
    const animatedElements = document.querySelectorAll('.fade-in-up-hidden, .fade-in-right-hidden');
    
    if (animatedElements.length === 0) return;
    
    // Create observer for animations
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const delay = entry.target.getAttribute('data-delay') || 0;
                setTimeout(() => {
                    if (entry.target.classList.contains('fade-in-up-hidden')) {
                        entry.target.classList.remove('fade-in-up-hidden');
                        entry.target.classList.add('fade-in-up');
                    } else if (entry.target.classList.contains('fade-in-right-hidden')) {
                        entry.target.classList.remove('fade-in-right-hidden');
                        entry.target.classList.add('fade-in-right');
                    }
                }, delay);
            }
        });
    }, { threshold: 0.1 });
    
    // Observe all elements with animation classes
    animatedElements.forEach(el => {
        observer.observe(el);
    });
}

/**
 * Setup global event listeners
 */
function setupEventListeners() {
    // Handle form submissions with AJAX
    document.querySelectorAll('form[data-ajax="true"]').forEach(form => {
        form.addEventListener('submit', handleAjaxForm);
    });
    
    // Handle dynamic content loading
    document.querySelectorAll('[data-load-content]').forEach(element => {
        element.addEventListener('click', loadDynamicContent);
    });
}

/**
 * Handle AJAX form submissions
 */
function handleAjaxForm(e) {
    e.preventDefault();
    const form = e.target;
    const url = form.action;
    const method = form.method || 'POST';
    const formData = new FormData(form);
    
    // Get CSRF token
    const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    
    // Create loading indicator
    const submitBtn = form.querySelector('[type="submit"]');
    const originalBtnText = submitBtn ? submitBtn.innerHTML : null;
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-circle-notch fa-spin me-2"></i>Processing...';
    }
    
    // Send request
    fetch(url, {
        method: method,
        body: formData,
        headers: {
            'X-CSRFToken': csrfToken
        }
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.json();
    })
    .then(data => {
        if (data.redirect) {
            window.location.href = data.redirect;
        } else if (data.success) {
            showToast(data.message || 'Operation successful', 'success');
            if (form.dataset.resetOnSuccess === 'true') {
                form.reset();
            }
        } else if (data.error) {
            showToast(data.error, 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('An error occurred. Please try again.', 'danger');
    })
    .finally(() => {
        // Restore button state
        if (submitBtn && originalBtnText) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalBtnText;
        }
    });
}

/**
 * Load dynamic content via AJAX
 */
function loadDynamicContent(e) {
    e.preventDefault();
    const element = e.target.closest('[data-load-content]');
    const url = element.getAttribute('data-load-content');
    const targetId = element.getAttribute('data-target');
    const target = document.getElementById(targetId);
    
    if (!url || !target) return;
    
    // Show loading indicator
    target.innerHTML = '<div class="text-center p-4"><div class="spinner-border text-primary" role="status"></div><p class="mt-2">Loading...</p></div>';
    
    // Get CSRF token
    const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    
    // Fetch content
    fetch(url, {
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': csrfToken
        }
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.text();
    })
    .then(html => {
        target.innerHTML = html;
        // Initialize components in loaded content
        initTooltips();
    })
    .catch(error => {
        console.error('Error:', error);
        target.innerHTML = '<div class="alert alert-danger">Failed to load content. Please try again.</div>';
    });
}

/**
 * Show toast notification
 * @param {string} message - Message to display
 * @param {string} type - Bootstrap color class (primary, success, danger, etc.)
 * @param {number} duration - Time in ms to show toast
 */
function showToast(message, type = 'primary', duration = 5000) {
    // Find or create toast container
    let toastContainer = document.querySelector('.toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
        toastContainer.style.zIndex = '1080';
        document.body.appendChild(toastContainer);
    }
    
    // Create toast element
    const toastId = 'toast-' + Date.now();
    const toast = document.createElement('div');
    toast.className = `toast show align-items-center text-white bg-${type} border-0`;
    toast.id = toastId;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    
    // Create toast content
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                <i class="fas fa-info-circle me-2"></i> ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;
    
    // Add toast to container
    toastContainer.appendChild(toast);
    
    // Auto close after duration
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }, duration);
    
    // Handle close button
    const closeBtn = toast.querySelector('.btn-close');
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            toast.classList.remove('show');
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        });
    }
} 