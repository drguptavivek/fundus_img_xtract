# Flash Toasts Script (`flash-toasts.js`)

This script manages the positioning and display of "flash" messages, which are rendered as Bootstrap Toasts. It ensures they appear correctly below the main navigation bar, even when the navbar's height changes due to window resizing or mobile view toggling.

## Purpose

1.  **Dynamic Positioning**: Toasts are positioned in the top-right corner. This script calculates the height of the main navbar and sets a CSS custom property (`--toast-top`) to offset the toast container, preventing it from being obscured.
2.  **Auto-Show Flashes**: It automatically finds and displays any toast elements present in the DOM when the page loads. This is used to show messages flashed from the server (e.g., via Flask's `flash()` function).

## How It Works

1.  **Event Listener**: The script waits for the `DOMContentLoaded` event to ensure the page structure is ready.

2.  **Position Calculation (`setToastTopOffset`)**:
    -   It finds the `.navbar` element.
    -   It measures the navbar's height using `getBoundingClientRect().height`.
    -   It sets a CSS custom property `--toast-top` on the `#flash-toasts` container element. The value is the navbar's height plus an 8px gap for spacing.

3.  **Responsive Updates**:
    -   The position is calculated on initial page load and on any `resize` event of the window.
    -   It also listens for Bootstrap's `shown.bs.collapse` and `hidden.bs.collapse` events on the navbar's collapsible element (`#navbarNav`). This ensures the toast position is updated correctly when the mobile navigation menu is opened or closed, as this can change the navbar's height.
    -   A fallback is included to re-calculate the position 250ms after a `.navbar-toggler` is clicked, in case the Bootstrap events are not available.

4.  **Auto-Showing Toasts**:
    -   The script selects all `.toast` elements inside the `#flash-toasts` container.
    -   It iterates through them and initializes a Bootstrap Toast instance for each one, setting it to `autohide` after 3 seconds (`delay: 3000`).
    -   It then calls `.show()` on each instance to make it appear.
    -   A simple fallback is included to manually add/remove the `.show` class if the Bootstrap JavaScript object is not found.

## Dependencies

-   **HTML**:
    -   A container element with `id="flash-toasts"`.
    -   A navbar element with the class `.navbar`.
    -   A collapsible element within the navbar, ideally with `id="navbarNav"`, for the most reliable responsive updates.
-   **JavaScript**:
    -   `bootstrap.bundle.min.js` (or at least `bootstrap.Toast`) should be loaded for the toast functionality.
-   **CSS**:
    -   The application's CSS should use the `--toast-top` variable to position the toast container.

## Example HTML Structure

This structure is typically placed in a base layout template (e.g., `base.html`).

```html
{# Main navigation bar #}
<nav class="navbar navbar-expand-lg ...">
  <div class="container-fluid">
    ...
    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav" ...>
      <span class="navbar-toggler-icon"></span>
    </button>
    <div class="collapse navbar-collapse" id="navbarNav">
      ...
    </div>
  </div>
</nav>

{# Toast container that the script targets #}
<div id="flash-toasts" class="toast-container position-fixed top-0 end-0 p-3" style="z-index: 1200; --toast-top: 64px;">
  {# Flashed messages from a framework like Flask would be rendered here #}
  <div class="toast text-bg-success border-0" role="alert" aria-live="assertive" aria-atomic="true">
    <div class="d-flex">
      <div class="toast-body">
        Your action was successful!
      </div>
      <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
    </div>
  </div>
</div>
```

## Usage

Include the script at the end of your `<body>` tag in your main layout file.

```html
<script src="{{ url_for('static', filename='js/flash-toasts.js') }}" defer></script>
```