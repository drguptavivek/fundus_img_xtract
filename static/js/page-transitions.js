/**
 * Page Transitions Enhancement
 *
 * Enhances the View Transitions API with browser support detection,
 * fallback handling, and optional advanced features for smooth navigation.
 *
 * Features:
 * - Browser support detection for View Transitions API
 * - Fallback handling for unsupported browsers
 * - Optional navigation direction detection
 * - Accessibility compliance
 * - Integration with existing navigation patterns
 */

(function() {
    'use strict';

    // Browser support detection
    const supportsViewTransitions = 'startViewTransition' in document;

    // Configuration
    const config = {
        enableFallbacks: true,
        debugMode: false,  // Disable debug mode to reduce console spam
        respectReducedMotion: true
    };

    // Logging utility
    function log(message, ...args) {
        if (config.debugMode) {
            console.log(`[PageTransitions] ${message}`, ...args);
        }
    }

    // Check if user prefers reduced motion
    function prefersReducedMotion() {
        if (!config.respectReducedMotion) return false;
        return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    // Check if any modals are currently open
    function hasActiveModals() {
        return document.querySelector('.modal.show') !== null;
    }

    // Check if any modal is currently opening or closing
    function hasModalTransitions() {
        const modals = document.querySelectorAll('.modal');
        return Array.from(modals).some(modal => {
            const style = window.getComputedStyle(modal);
            return style.transition !== 'none' && style.transitionDuration !== '0s';
        });
    }

    // Get current page identifier for navigation direction
    function getPageIdentifier() {
        // Use pathname as primary identifier
        return window.location.pathname;
    }

    // Determine navigation direction for enhanced transitions
    function getNavigationDirection(from, to) {
        // Simple heuristic: based on URL structure
        if (from === to) return 'same';

        // Check for admin pages
        if (to.includes('/admin') && !from.includes('/admin')) return 'to-admin';
        if (!to.includes('/admin') && from.includes('/admin')) return 'from-admin';

        // Check for detail vs list pages
        if (to.includes('/detail/') || to.includes('/edit/')) return 'to-detail';
        if (from.includes('/detail/') || from.includes('/edit/')) return 'from-detail';

        return 'default';
    }

    // Initialize View Transitions API enhancements
    function initViewTransitions() {
        log('Initializing View Transitions API');
        log('Browser support:', supportsViewTransitions ? 'Supported' : 'Fallback mode');
        log('Reduced motion preference:', prefersReducedMotion() ? 'Yes' : 'No');

        if (!supportsViewTransitions && config.enableFallbacks) {
            initFallbacks();
        }

        // Listen for navigation events for analytics or debugging
        if (supportsViewTransitions) {
            setupNavigationListeners();
        }

        // Setup modal event listeners to prevent conflicts
        setupModalListeners();

        // Add page transition classes for enhanced styling
        addTransitionClasses();
    }

    // Setup fallback behavior for browsers without View Transitions API
    function initFallbacks() {
        log('Setting up fallback transitions');

        // Add fallback class to body for CSS targeting
        document.body.classList.add('no-view-transitions');

        // Add subtle fade transitions to main content
        const style = document.createElement('style');
        style.textContent = `
            body.no-view-transitions .main-content {
                transition: opacity 0.2s ease-in-out;
            }
            body.no-view-transitions.page-transitioning .main-content {
                opacity: 0.7;
            }
        `;
        document.head.appendChild(style);

        // Hook into navigation for manual transitions
        setupFallbackNavigation();
    }

    // Setup fallback navigation handling
    function setupFallbackNavigation() {
        let currentPath = window.location.pathname;

        // Monitor navigation changes
        const originalPushState = history.pushState;
        const originalReplaceState = history.replaceState;

        history.pushState = function(...args) {
            const result = originalPushState.apply(this, args);
            handleNavigationChange(currentPath, window.location.pathname);
            currentPath = window.location.pathname;
            return result;
        };

        history.replaceState = function(...args) {
            const result = originalReplaceState.apply(this, args);
            handleNavigationChange(currentPath, window.location.pathname);
            currentPath = window.location.pathname;
            return result;
        };

        window.addEventListener('popstate', () => {
            handleNavigationChange(currentPath, window.location.pathname);
            currentPath = window.location.pathname;
        });
    }

    // Handle navigation changes for fallback transitions
    function handleNavigationChange(from, to) {
        if (from === to) return;

        // Check for active modals - skip transitions if found
        if (hasActiveModals() || document.body.classList.contains('modal-active')) {
            // Don't add transition classes if modals are active
            return;
        }

        const direction = getNavigationDirection(from, to);
        log(`Navigation change: ${from} → ${to} (${direction})`);

        // Add transitioning class
        document.body.classList.add('page-transitioning');

        // Remove transitioning class after a short delay
        setTimeout(() => {
            document.body.classList.remove('page-transitioning');
        }, 200);
    }

    // Setup navigation listeners for supported browsers
    function setupNavigationListeners() {
        let lastPath = window.location.pathname;

        // Listen for navigation events if available
        if ('navigation' in window && 'addEventListener' in window.navigation) {
            window.navigation.addEventListener('navigate', (event) => {
                // Check for active modals before allowing navigation
                if (hasActiveModals() || hasModalTransitions()) {
                    log('Preventing navigation - active modal detected');
                    event.preventDefault();
                    return;
                }

                const to = new URL(event.destination.url).pathname;
                const direction = getNavigationDirection(lastPath, to);
                log(`Navigate event: ${lastPath} → ${to} (${direction})`);
                lastPath = to;
            });
        }
    }

    // Setup modal event listeners to prevent conflicts
    function setupModalListeners() {
        // Remove page transitioning class when modals start showing
        document.addEventListener('show.bs.modal', function(event) {
            document.body.classList.remove('page-transitioning');
            document.body.classList.add('modal-active');
        });

        // Ensure page transitioning class is removed when modals are fully shown
        document.addEventListener('shown.bs.modal', function(event) {
            document.body.classList.remove('page-transitioning');
            document.body.classList.add('modal-active');
        });

        // Handle modal hidden events - allow transitions after modal closes
        document.addEventListener('hidden.bs.modal', function(event) {
            document.body.classList.remove('modal-active');
        });

        // Handle modal hide events - prepare for transition re-enable
        document.addEventListener('hide.bs.modal', function(event) {
            document.body.classList.remove('page-transitioning');
        });
    }

    // Add transition classes to main content for styling
    function addTransitionClasses() {
        const mainContent = document.querySelector('.main-content');
        if (mainContent) {
            mainContent.classList.add('page-transition-enabled');
            log('Added transition classes to main content');
        }
    }

    // Public API for manual transition control
    window.PageTransitions = {
        // Check if View Transitions API is supported
        supported: supportsViewTransitions,

        // Enable/disable debug mode
        setDebugMode: function(enabled) {
            config.debugMode = !!enabled;
            log(`Debug mode ${enabled ? 'enabled' : 'disabled'}`);
        },

        // Check if reduced motion is preferred
        prefersReducedMotion: prefersReducedMotion,

        // Check if any modals are currently active
        hasActiveModals: hasActiveModals,

        // Check if any modal transitions are in progress
        hasModalTransitions: hasModalTransitions,

        // Manually trigger a transition (advanced usage)
        triggerTransition: function(callback) {
            // Skip transitions if modals are active
            if (hasActiveModals() || hasModalTransitions()) {
                log('Skipping manual transition - active modal detected');
                callback();
                return { finished: Promise.resolve() };
            }

            if (supportsViewTransitions && !prefersReducedMotion()) {
                return document.startViewTransition(callback);
            } else {
                // Fallback: just execute the callback
                callback();
                return { finished: Promise.resolve() };
            }
        },

        // Get current configuration
        getConfig: function() {
            return { ...config };
        },

        // Update configuration
        updateConfig: function(newConfig) {
            Object.assign(config, newConfig);
            log('Configuration updated:', config);
        }
    };

    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initViewTransitions);
    } else {
        initViewTransitions();
    }

    // Log initialization
    log('Page Transitions module loaded');

})();