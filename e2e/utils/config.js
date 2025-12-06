// @ts-check
/**
 * Configuration utilities for E2E tests
 */

/**
 * Get the base URL for the application from environment variables
 * @returns {string} The base URL
 */
export function getBaseUrl() {
  return process.env.BASE_URL || 'http://127.0.0.1:5001';
}

/**
 * Get the login URL for the application
 * @returns {string} The login URL
 */
export function getLoginUrl() {
  return `${getBaseUrl()}/auth/login`;
}

/**
 * Get the API base URL for the application
 * @returns {string} The API base URL
 */
export function getApiBaseUrl() {
  return `${getBaseUrl()}/api`;
}

/**
 * Get the search images URL for the application
 * @returns {string} The search images URL
 */
export function getSearchImagesUrl() {
  return `${getBaseUrl()}/search/images`;
}

/**
 * Get the dashboard URL for the application
 * @returns {string} The dashboard URL
 */
export function getDashboardUrl() {
  return `${getBaseUrl()}/dashboard`;
}