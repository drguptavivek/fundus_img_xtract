/**
 * CAPTCHA functionality for login page
 */
 
document.addEventListener('DOMContentLoaded', function() {
    const captchaImg = document.getElementById('captcha-img');
    const captchaInput = document.getElementById('captcha');
    const audioBtn = document.getElementById('audio-captcha-btn');
    const refreshBtn = document.getElementById('refresh-captcha-btn');
    let currentAudio = null;
    
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
    
    // Audio CAPTCHA functionality
    if (audioBtn) {
        audioBtn.addEventListener('click', function() {
            playCaptchaAudio();
        });
    }
    
    /**
     * Play audio CAPTCHA
     */
    function playCaptchaAudio() {
        // Stop any currently playing audio
        if (currentAudio) {
            currentAudio.pause();
            currentAudio = null;
        }
        
        fetch('/captcha-audio')
            .then(response => response.json())
            .then(data => {
                if (data.audio) {
                    // Create audio element and play
                    const audio = new Audio(data.audio);
                    currentAudio = audio;
                    audio.play().catch(error => {
                        console.error('Error playing audio CAPTCHA:', error);
                    });
                    
                    // Clean up after audio finishes
                    audio.addEventListener('ended', function() {
                        currentAudio = null;
                    });
                }
            })
            .catch(error => {
                console.error('Error fetching audio CAPTCHA:', error);
            });
    }
    
    /**
     * Refresh CAPTCHA image and audio availability
     */
    function refreshCaptcha() {
        fetch('/refresh-captcha')
            .then(response => response.json())
            .then(data => {
                if (data.image) {
                    captchaImg.src = data.image;
                    // Clear CAPTCHA input field
                    if (captchaInput) {
                        captchaInput.value = '';
                        captchaInput.focus();
                    }
                    // Update audio button visibility
                    if (audioBtn) {
                        audioBtn.style.display = data.audio_available ? 'inline-block' : 'none';
                    }
                }
            })
            .catch(error => {
                console.error('Error refreshing CAPTCHA:', error);
                // Fallback: reload the page if fetch fails
                window.location.reload();
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