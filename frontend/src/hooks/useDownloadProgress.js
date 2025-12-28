/** Custom hook for managing download progress */
import { useState, useEffect, useRef } from 'react';
import { getDownloadProgress } from '../services/api';

/**
 * Hook to track download progress
 * @param {string} fileId - File ID to track
 * @param {boolean} enabled - Whether to poll for progress
 * @returns {Object} Progress state and controls
 */
export const useDownloadProgress = (fileId, enabled = true) => {
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);

  useEffect(() => {
    if (!fileId || !enabled) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }

    const pollProgress = async () => {
      try {
        const progressData = await getDownloadProgress(fileId);
        setProgress(progressData);
        setError(null);

        // Stop polling if download is complete, cancelled, or errored
        if (
          progressData.status === 'completed' ||
          progressData.status === 'cancelled' ||
          progressData.status === 'error'
        ) {
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
        }
      } catch (err) {
        setError(err.message || 'Failed to get progress');
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      }
    };

    // Poll immediately, then every 500ms
    pollProgress();
    intervalRef.current = setInterval(pollProgress, 500);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [fileId, enabled]);

  const stopPolling = () => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  };

  return { progress, error, stopPolling };
};


