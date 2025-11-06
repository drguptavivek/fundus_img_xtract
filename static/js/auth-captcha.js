/**
 * CAPTCHA functionality for login page
 */
 
document.addEventListener('DOMContentLoaded', function() {
    const captchaImg = document.getElementById('captcha-img');
    const captchaInput = document.getElementById('captcha');
    const refreshBtn = document.getElementById('refresh-captcha-btn');
    let refreshRequestInProgress = false;  // Prevent multiple refresh requests
    
    if (captchaImg) {
        // Add click event to refresh CAPTCHA
        captchaImg.addEventListener('click', function() {
            refreshCaptcha();
        });
        
        // Add hover effect to indicate it's clickable
        captchaImg.style.cursor = 'pointer';
        captchaImg.title = 'Click to refresh CAPTCHA';
    }
    
    // Refresh button functionality
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            refreshCaptcha();
        });
    }
    
    /**
     * Refresh CAPTCHA image
     */
    function refreshCaptcha() {
        // Prevent multiple refresh requests
        if (refreshRequestInProgress) {
            return;
        }
        
        refreshRequestInProgress = true;
        
        fetch('/refresh-captcha')
            .then(response => response.json())
            .then(data => {
                if (data && data.image) {
                    captchaImg.src = data.image;
                    // Clear CAPTCHA input field
                    if (captchaInput) {
                        captchaInput.value = '';
                        captchaInput.focus();
                    }
                }
            })
            .catch(error => {
                console.error('Error refreshing CAPTCHA:', error);
                // Fallback: reload the page if fetch fails
                window.location.reload();
            })
            .finally(() => {
                refreshRequestInProgress = false;
            });
    }
    
    // Add keyboard shortcut: Ctrl+R or F5 when on CAPTCHA field refreshes it
    if (captchaInput) {
        captchaInput.addEventListener('keydown', function(e) {
            if ((e.ctrlKey && e.key === 'r') || e.key === 'F5') {
                e.preventDefault();
                refreshCaptcha();
            }
        });
    }
});