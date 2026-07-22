/**
 * Shared formatting utilities for Creonnect frontend pages.
 * Import from here instead of defining locally in each page.
 */

/**
 * Format a numeric value as a locale string (e.g., 1234567 → "1,234,567").
 * Returns "N/A" for non-numeric or NaN inputs.
 */
export function formatNumber(value) {
    if (typeof value !== 'number' || Number.isNaN(value)) {
        return 'N/A'
    }
    return value.toLocaleString('en-US')
}

/**
 * Format a ratio (0–1) as a percentage string (e.g., 0.123 → "12.3%").
 * Returns "N/A" for non-numeric or NaN inputs.
 */
export function formatPercent(value) {
    if (typeof value !== 'number' || Number.isNaN(value)) {
        return 'N/A'
    }
    return `${(value * 100).toFixed(1)}%`
}

/**
 * Format an ISO date string or Date-coercible value as a readable date.
 * @param {string|any} value - The date value to format.
 * @param {Intl.DateTimeFormatOptions} [options] - toLocaleDateString options.
 * @returns {string} Formatted date or "Date unavailable".
 */
export function formatDate(value, options = { month: 'long', day: 'numeric', year: 'numeric' }) {
    if (!value) {
        return 'Date unavailable'
    }
    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) {
        return 'Date unavailable'
    }
    return parsed.toLocaleDateString('en-US', options)
}

/**
 * Format a snake_case or underscore-separated string as Title Case words.
 * E.g., "content_quality" → "Content Quality".
 * Returns "Unknown" for non-string or empty inputs.
 */
export function formatPillarName(value) {
    if (typeof value !== 'string' || !value.trim()) {
        return 'Unknown'
    }
    return value
        .split('_')
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ')
}

/**
 * Format a number to a fixed number of decimal places.
 * Returns "N/A" for non-numeric or NaN inputs.
 */
export function formatDecimal(value, digits = 2) {
    if (typeof value !== 'number' || Number.isNaN(value)) {
        return 'N/A'
    }
    return value.toFixed(digits)
}