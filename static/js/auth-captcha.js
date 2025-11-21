/**
 * CAPTCHA functionality for login page
 */
 
document.addEventListener('DOMContentLoaded', function() {
    const captchaImg = document.getElementById('captcha-img');
    const captchaInput = document.getElementById('captcha');
    const refreshBtn = document.getElementById('refresh-captcha-btn');
    const playAudioBtn = document.getElementById('play-audio-btn');
    const signinBtn = document.getElementById('signin-btn');
    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : null;
    let captchaAudio = null; // Will be created dynamically when needed
    let currentCaptchaData = null; // Store the latest CAPTCHA data
    let refreshRequestInProgress = false;  // Prevent multiple refresh requests
    let captchaLoaded = false;  // Track if CAPTCHA has successfully loaded
    let audioLoaded = false;  // Track if audio has successfully loaded

    /**
     * Utility function to show flash toast with fallback to alert
     */
    function showToast(message, type = 'info') {
        if (window.showFlashToast) {
            window.showFlashToast(message, type);
        } else {
            // Fallback to console for development
            console.log(`[${type.toUpperCase()}] ${message}`);
            // For critical errors, still use alert as fallback
            if (type === 'error') {
                alert(message);
            }
        }
    }

    
    /**
     * Update the audio button based on audio availability and loading state
     */
    function updateAudioButton() {
        if (playAudioBtn) {
            if (audioLoaded) {
                playAudioBtn.disabled = false;
                playAudioBtn.textContent = '🔊 Play Audio';
                playAudioBtn.title = 'Play CAPTCHA audio';
                playAudioBtn.classList.remove('disabled');
            } else if (captchaLoaded) {
                // CAPTCHA loaded but audio not available
                playAudioBtn.disabled = true;
                playAudioBtn.textContent = '🔊 Audio Unavailable';
                playAudioBtn.title = 'Audio CAPTCHA not available for this code';
                playAudioBtn.classList.add('disabled');
            } else {
                // Still loading CAPTCHA
                playAudioBtn.disabled = true;
                playAudioBtn.textContent = '🔊 Loading Audio...';
                playAudioBtn.title = 'Loading CAPTCHA audio...';
                playAudioBtn.classList.add('disabled');
            }
        }
    }

    // On page load, refresh CAPTCHA to get the first one
    refreshCaptcha();

    // Initialize button states
    updateFormValidation();
    updateAudioButton();

    // Hide traditional alerts and show only flash toasts
    const existingAlerts = document.querySelectorAll('.alert');
    existingAlerts.forEach((alert) => {
        const message = alert.textContent.trim();
        if (message && !message.includes('Close')) {
            // Determine toast type based on alert class
            let toastType = 'info';
            if (alert.classList.contains('alert-danger') || alert.classList.contains('alert-error')) {
                toastType = 'error';
            } else if (alert.classList.contains('alert-warning')) {
                toastType = 'warning';
            } else if (alert.classList.contains('alert-success')) {
                toastType = 'success';
            }

            // Show as toast immediately
            showToast(message, toastType);
        }
        // Hide the original alert immediately
        alert.style.display = 'none';
    });

    // Auto-capitalize CAPTCHA input
    if (captchaInput) {
        captchaInput.addEventListener('input', function(e) {
            // Convert to uppercase as user types
            e.target.value = e.target.value.toUpperCase();
        });
    }

    /**
     * Check if all mandatory fields are filled and valid, then update sign-in button
     */
    function updateFormValidation() {
        const username = document.getElementById('username');
        const password = document.getElementById('password');
        const captcha = document.getElementById('captcha');

        // Check if fields exist and are not empty
        const isUsernamePresent = username && username.value.trim() !== '';
        const isPasswordPresent = password && password.value.trim() !== '';
        const isCaptchaPresent = captcha && captcha.value.trim() !== '';

        // Check field length limits
        const isUsernameValid = isUsernamePresent && username.value.length <= 50;
        const isPasswordValid = isPasswordPresent && password.value.length <= 255;
        const isCaptchaValid = isCaptchaPresent && captcha.value.length <= 10;

        // Determine validation state
        let validationMessage = '';
        let allFieldsValid = false;

        if (!captchaLoaded) {
            validationMessage = 'Loading CAPTCHA...';
        } else if (!isUsernamePresent) {
            validationMessage = 'Username required';
        } else if (!isUsernameValid) {
            validationMessage = 'Username too long (max 50)';
        } else if (!isPasswordPresent) {
            validationMessage = 'Password required';
        } else if (!isPasswordValid) {
            validationMessage = 'Password too long (max 255)';
        } else if (!isCaptchaPresent) {
            validationMessage = 'CAPTCHA required';
        } else if (!isCaptchaValid) {
            validationMessage = 'CAPTCHA too long (max 10)';
        } else {
            validationMessage = 'Sign in';
            allFieldsValid = true;
        }

        // Update sign-in button state
        if (signinBtn) {
            signinBtn.disabled = !allFieldsValid;
            signinBtn.textContent = validationMessage;
            signinBtn.title = allFieldsValid ? 'Sign in to your account' : validationMessage;

            if (allFieldsValid) {
                signinBtn.classList.remove('disabled');
            } else {
                signinBtn.classList.add('disabled');
            }
        }

        // Set custom validity for HTML5 validation
        if (username) {
            if (isUsernamePresent && !isUsernameValid) {
                username.setCustomValidity('Username must be 50 characters or less');
            } else {
                username.setCustomValidity('');
            }
        }

        if (password) {
            if (isPasswordPresent && !isPasswordValid) {
                password.setCustomValidity('Password must be 255 characters or less');
            } else {
                password.setCustomValidity('');
            }
        }

        if (captcha) {
            if (isCaptchaPresent && !isCaptchaValid) {
                captcha.setCustomValidity('CAPTCHA must be 10 characters or less');
            } else {
                captcha.setCustomValidity('');
            }
        }

        return allFieldsValid;
    }

    // Add input event listeners to all form fields for real-time validation
    const formFields = ['username', 'password', 'captcha'];
    formFields.forEach(fieldId => {
        const field = document.getElementById(fieldId);
        if (field) {
            field.addEventListener('input', updateFormValidation);
            field.addEventListener('blur', updateFormValidation);
        }
    });

    /**
     * Ensure login form always carries a CSRF token value.
     * Some automation tools submit the form without re-reading the hidden input,
     * so we inject/populate it from the meta tag as a fallback.
     */
    const loginForm = document.querySelector('form[method=\"post\"]');
    function ensureCsrfTokenOnForm() {
        if (!loginForm) return;
        let csrfInput = loginForm.querySelector('input[name=\"csrf_token\"]');
        if (!csrfInput) {
            csrfInput = document.createElement('input');
            csrfInput.type = 'hidden';
            csrfInput.name = 'csrf_token';
            loginForm.prepend(csrfInput);
        }
        if (!csrfInput.value && csrfToken) {
            csrfInput.value = csrfToken;
        }
    }
    ensureCsrfTokenOnForm();

    // Add form submission listener to handle validation errors
    if (loginForm) {
        loginForm.addEventListener('submit', function(e) {
            // Client-side validation before submission
            const username = document.getElementById('username');
            const password = document.getElementById('password');
            const captcha = document.getElementById('captcha');

            // Check if fields are filled
            if (!username || !username.value.trim()) {
                e.preventDefault();
                showToast('Please enter your username', 'warning');
                username?.focus();
                return false;
            }

            if (!password || !password.value.trim()) {
                e.preventDefault();
                showToast('Please enter your password', 'warning');
                password?.focus();
                return false;
            }

            if (!captcha || !captcha.value.trim()) {
                e.preventDefault();
                showToast('Please enter the CAPTCHA code', 'warning');
                captcha?.focus();
                return false;
            }

            // Check field length limits
            if (username.value.length > 50) {
                e.preventDefault();
                showToast('Username must be 50 characters or less', 'error');
                username?.focus();
                return false;
            }

            if (password.value.length > 255) {
                e.preventDefault();
                showToast('Password must be 255 characters or less', 'error');
                password?.focus();
                return false;
            }

            if (captcha.value.length > 10) {
                e.preventDefault();
                showToast('CAPTCHA must be 10 characters or less', 'error');
                captcha?.focus();
                return false;
            }

            // If we get here, validation passed
            // Don't clear CAPTCHA input here - let the backend handle it
            // If login fails, backend will show error and generate new CAPTCHA
            // If login succeeds, user will be redirected anyway

            return true;
        });
    }
    
    if (captchaImg) {
        // Add click event to refresh CAPTCHA
        captchaImg.addEventListener('click', function() {
            // Reset states during refresh
            captchaLoaded = false;
            audioLoaded = false;
            updateFormValidation();
            updateAudioButton();
            refreshCaptcha();
        });

        // Add hover effect to indicate it's clickable
        captchaImg.style.cursor = 'pointer';
        captchaImg.title = 'Click to refresh CAPTCHA';
    }

    // Refresh button functionality
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            // Reset states during refresh
            captchaLoaded = false;
            audioLoaded = false;
            updateFormValidation();
            updateAudioButton();
            refreshCaptcha();
        });
    }
    
    // Audio button functionality - play audio directly
    if (playAudioBtn) {
        playAudioBtn.addEventListener('click', function() {
            createAndPlayAudio();
        });
    }
    
    /**
     * Refresh CAPTCHA image and store audio data
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
                    // Update the image
                    captchaImg.src = data.image;

                    // Store the new CAPTCHA data (including audio)
                    currentCaptchaData = data;

                    // Clear CAPTCHA input field
                    if (captchaInput) {
                        captchaInput.value = '';
                        captchaInput.focus();
                    }

                    // Handle audio availability
                    if (data.audio && data.audio !== null) {
                        // Audio is available
                        audioLoaded = true;
                        currentCaptchaData = data;

                        // If audio element exists, remove it and create a new one
                        if (captchaAudio) {
                            captchaAudio.remove();
                            captchaAudio = null;
                        }
                    } else {
                        // Audio is not available
                        audioLoaded = false;
                        console.log('Audio CAPTCHA not available for this request');
                    }

                    // Mark CAPTCHA as loaded and update both buttons
                    captchaLoaded = true;
                    updateFormValidation();
                    updateAudioButton();

                                    }
            })
            .catch(error => {
                console.error('Error refreshing CAPTCHA:', error);

                // Reset states on error
                captchaLoaded = false;
                audioLoaded = false;

                // Update buttons to show error state
                updateFormValidation();
                updateAudioButton();

                // Fallback: reload the page if fetch fails
                window.location.reload();
            })
            .finally(() => {
                refreshRequestInProgress = false;
            });
    }
    

    
    /**
     * Create a hidden audio element and play the audio
     */
    function createAndPlayAudio() {
        // Check if we have current CAPTCHA data with audio
        if (!currentCaptchaData || !currentCaptchaData.audio) {
            showToast('No audio available for the current CAPTCHA. Please try refreshing.', 'warning');
            return;
        }

        console.log('Playing audio with data:', currentCaptchaData.audio.substring(0, 100) + '...');

        // Remove any existing audio element
        const existingAudio = document.getElementById('captcha-audio');
        if (existingAudio) {
            existingAudio.remove();
        }

        // Create a hidden audio element
        captchaAudio = document.createElement('audio');
        captchaAudio.id = 'captcha-audio';
        captchaAudio.preload = 'auto';
        captchaAudio.style.display = 'none'; // Hide the audio element

        // Set the src directly
        captchaAudio.src = currentCaptchaData.audio;

        // Add to body (not to audio container to avoid layout issues)
        document.body.appendChild(captchaAudio);

        // Add event listeners for better debugging
        captchaAudio.addEventListener('loadstart', () => {
            console.log('Audio loading started');
            updatePlayButtonState('loading');
        });

        captchaAudio.addEventListener('loadedmetadata', () => {
            console.log('Audio metadata loaded');
        });

        captchaAudio.addEventListener('canplay', () => {
            console.log('Audio can play - attempting to play');
            updatePlayButtonState('playing');
            captchaAudio.play().then(() => {
                console.log('Audio playback successful');
                updatePlayButtonState('playing');
            }).catch(error => {
                console.error('Error playing CAPTCHA audio:', error);
                console.error('Audio error code:', captchaAudio.error ? captchaAudio.error.code : 'No error code');
                updatePlayButtonState('error');
                // Try alternative method
                setTimeout(() => {
                    captchaAudio.play().catch(err => {
                        console.error('Retry failed:', err);
                        updatePlayButtonState('error');
                        showToast('Could not play audio. Your browser may not support audio playback.', 'error');
                    });
                }, 100);
            });
        });

        captchaAudio.addEventListener('ended', () => {
            console.log('Audio playback ended');
            updatePlayButtonState('ready');
        });

        captchaAudio.addEventListener('error', (e) => {
            console.error('Audio element error:', e);
            console.error('Audio error details:', captchaAudio.error);
            console.error('Audio error code:', captchaAudio.error ? captchaAudio.error.code : 'No error code');
            console.error('Audio error message:', captchaAudio.error ? captchaAudio.error.message : 'No error message');

            updatePlayButtonState('error');

            // Try to decode the base64 data to see if it's valid
            try {
                const base64Data = currentCaptchaData.audio.split(',')[1];
                if (base64Data) {
                    const decodedData = atob(base64Data);
                    console.log('Base64 decoded successfully, length:', decodedData.length);
                }
            } catch (decodeError) {
                console.error('Base64 decode error:', decodeError);
            }

            showToast('Could not load audio. The audio data may be corrupted. Please try refreshing the CAPTCHA.', 'error');
        });
    }

    /**
     * Update the play button state during audio operations
     */
    function updatePlayButtonState(state) {
        if (playAudioBtn) {
            switch (state) {
                case 'loading':
                    playAudioBtn.disabled = true;
                    playAudioBtn.textContent = '🔊 Loading...';
                    playAudioBtn.title = 'Loading audio...';
                    break;
                case 'playing':
                    playAudioBtn.disabled = false;
                    playAudioBtn.textContent = '🔊 Playing...';
                    playAudioBtn.title = 'Audio is playing...';
                    break;
                case 'ready':
                    playAudioBtn.disabled = false;
                    playAudioBtn.textContent = '🔊 Play Audio';
                    playAudioBtn.title = 'Play CAPTCHA audio';
                    break;
                case 'error':
                    playAudioBtn.disabled = true;
                    playAudioBtn.textContent = '🔊 Error';
                    playAudioBtn.title = 'Audio playback error';
                    break;
            }
        }
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

    // Add a test function to check browser audio support (accessible from console)
    window.testAudioSupport = function() {
        console.log('Testing browser audio support...');
        const testAudio = new Audio();
        testAudio.src = 'data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtmMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmwhBSuBzvLZiTYIG2m98OScTgwOUarm7blmGgU7k9n1unEiBC13yO/eizEIHWq+8+OWT';

        testAudio.addEventListener('canplay', () => {
            console.log('Test audio can play - browser supports audio');
            testAudio.play().then(() => {
                console.log('Test audio played successfully');
            }).catch(err => {
                console.error('Test audio play failed:', err);
            });
        });

        testAudio.addEventListener('error', (e) => {
            console.error('Test audio error:', e);
            console.error('Test audio error details:', testAudio.error);
        });

        console.log('Test audio element created:', testAudio);
        return testAudio;
    };
});
