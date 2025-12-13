import { useState, useEffect, useCallback } from 'react';

/**
 * Custom hook for fetching data with loading and error states.
 *
 * @param {Function} fetchFn - Async function that fetches data
 * @param {Object} options - Hook options
 * @param {any} options.defaultValue - Default value for data (default: null)
 * @param {boolean} options.immediate - Whether to fetch immediately on mount (default: true)
 * @param {Array} options.deps - Dependencies array for refetching (default: [])
 * @returns {Object} { data, loading, error, refetch }
 */
export function useFetchData(fetchFn, options = {}) {
  const { defaultValue = null, immediate = true, deps = [] } = options;

  const [data, setData] = useState(defaultValue);
  const [loading, setLoading] = useState(immediate);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchFn();
      setData(result);
      return result;
    } catch (err) {
      setError(err.message || 'An error occurred');
      return defaultValue;
    } finally {
      setLoading(false);
    }
  }, [fetchFn, defaultValue]);

  useEffect(() => {
    if (immediate) {
      fetchData();
    }
  }, [immediate, ...deps]);

  return { data, loading, error, refetch: fetchData, setData };
}

export default useFetchData;
