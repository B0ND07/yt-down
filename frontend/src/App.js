import React, { useState } from 'react';
import axios from 'axios';
import './App.css';

function App() {
  const [url, setUrl] = useState('');
  const [videoInfo, setVideoInfo] = useState(null);
  const [selectedFormat, setSelectedFormat] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [downloadStatus, setDownloadStatus] = useState('');
  const [playlistInfo, setPlaylistInfo] = useState(null);
  const [selectedVideos, setSelectedVideos] = useState(new Set());
  const [downloadProgress, setDownloadProgress] = useState([]);
  const [zipUrl, setZipUrl] = useState(null);
  const [totalDownloadedSize, setTotalDownloadedSize] = useState(0);

  const API_BASE = 'http://localhost:8000';

  const fetchVideoInfo = async () => {
    if (!url.trim()) {
      setError('Please enter a YouTube URL');
      return;
    }

    setLoading(true);
    setError('');
    setVideoInfo(null);
    setSelectedFormat(null);
    setDownloadStatus('');
    setPlaylistInfo(null);
    setSelectedVideos(new Set());

    // Check if it's a playlist
    if (url.includes('playlist') || url.includes('&list=')) {
      try {
        const response = await axios.post(`${API_BASE}/api/playlist-info`, { url });
        setPlaylistInfo(response.data);
        
        // Fetch formats from first video for quality selection
        if (response.data.videos && response.data.videos.length > 0) {
          const firstVideoUrl = response.data.videos[0].url;
          const formatResponse = await axios.post(`${API_BASE}/api/video-info`, { url: firstVideoUrl });
          setVideoInfo(formatResponse.data);
          if (formatResponse.data.formats && formatResponse.data.formats.length > 0) {
            setSelectedFormat(formatResponse.data.formats[0]);
          }
        }
        
        // If it's a single video treated as playlist, get its formats
        if (!response.data.is_playlist && response.data.videos.length === 1) {
          const videoResponse = await axios.post(`${API_BASE}/api/video-info`, { url });
          setVideoInfo(videoResponse.data);
          if (videoResponse.data.formats && videoResponse.data.formats.length > 0) {
            setSelectedFormat(videoResponse.data.formats[0]);
          }
        }
      } catch (err) {
        const errorMsg = err.response?.data?.detail;
        setError(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg) || 'Failed to fetch playlist information');
      } finally {
        setLoading(false);
      }
      return;
    }

    // Single video

    try {
      const response = await axios.post(`${API_BASE}/api/video-info`, { url });
      setVideoInfo(response.data);
      if (response.data.formats && response.data.formats.length > 0) {
        setSelectedFormat(response.data.formats[0]);
      }
    } catch (err) {
      const errorMsg = err.response?.data?.detail;
      setError(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg) || 'Failed to fetch video information');
    } finally {
      setLoading(false);
    }
  };

  const handleDirectDownload = async () => {
    if (!selectedFormat) {
      setError('Please select a quality');
      return;
    }

    setLoading(true);
    setError('');
    setDownloadStatus('Getting direct link...');

    try {
      const response = await axios.post(`${API_BASE}/api/direct-link`, {
        url,
        quality: String(selectedFormat.quality || selectedFormat.resolution || 'best'),
        format_id: selectedFormat.format_id ? String(selectedFormat.format_id) : null
      });

      // Open direct link in new tab
      window.open(response.data.direct_url, '_blank');
      setDownloadStatus('Direct link opened in new tab!');
    } catch (err) {
      const errorMsg = err.response?.data?.detail;
      setError(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg) || 'Failed to get direct link');
      setDownloadStatus('');
    } finally {
      setLoading(false);
    }
  };

  const handleServerDownload = async () => {
    if (!selectedFormat) {
      setError('Please select a quality');
      return;
    }

    setLoading(true);
    setError('');
    setDownloadStatus(`📥 Starting download...`);

    try {
      // Start download and get file_id
      const response = await axios.post(`${API_BASE}/api/download`, {
        url,
        quality: String(selectedFormat.quality || selectedFormat.resolution || 'best'),
        format_id: selectedFormat.format_id ? String(selectedFormat.format_id) : null
      });

      const fileId = response.data.file_id;
      
      // Poll for progress
      const progressInterval = setInterval(async () => {
        try {
          const progressRes = await axios.get(`${API_BASE}/api/progress/${fileId}`);
          const progress = progressRes.data;
          
          if (progress.status === 'downloading' && progress.total_bytes > 0) {
            const percent = Math.round(progress.percentage);
            const downloaded = formatFileSize(progress.downloaded_bytes);
            setDownloadStatus(`📥 Downloading ${percent}% | ${downloaded}`);
          } else if (progress.status === 'completed') {
            clearInterval(progressInterval);
            setDownloadStatus(`✓ Downloaded ${formatFileSize(progress.filesize)} | Preparing file...`);
            
            // Trigger file download
            const downloadUrl = `${API_BASE}/api/download-file/${fileId}`;
            const link = document.createElement('a');
            link.href = downloadUrl;
            link.download = progress.filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            setDownloadStatus('✓ File ready for download!');
            setTimeout(() => setDownloadStatus(''), 3000);
            setLoading(false);
          } else if (progress.status === 'error') {
            clearInterval(progressInterval);
            setError(progress.error || 'Download failed');
            setDownloadStatus('');
            setLoading(false);
          }
        } catch (err) {
          clearInterval(progressInterval);
          setError('Failed to get progress');
          setDownloadStatus('');
          setLoading(false);
        }
      }, 500);

    } catch (err) {
      const errorMsg = err.response?.data?.detail;
      setError(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg) || 'Failed to download video');
      setDownloadStatus('');
    } finally {
      setLoading(false);
    }
  };

  const toggleVideoSelection = (videoId) => {
    const newSelected = new Set(selectedVideos);
    if (newSelected.has(videoId)) {
      newSelected.delete(videoId);
    } else {
      newSelected.add(videoId);
    }
    setSelectedVideos(newSelected);
  };

  const selectAllVideos = () => {
    if (playlistInfo && playlistInfo.videos) {
      setSelectedVideos(new Set(playlistInfo.videos.map(v => v.id)));
    }
  };

  const deselectAllVideos = () => {
    setSelectedVideos(new Set());
  };

  const handleBatchDownload = async () => {
    if (selectedVideos.size === 0) {
      setError('Please select at least one video');
      return;
    }

    const selectedUrls = playlistInfo.videos
      .filter(v => selectedVideos.has(v.id))
      .map(v => v.url);

    setLoading(true);
    setError('');
    setDownloadProgress([]);
    setZipUrl(null);
    setTotalDownloadedSize(0);

    try {
      // Download videos one by one with progress updates
      const results = [];
      const totalVideos = selectedUrls.length;
      let downloadedSize = 0;
      
      for (let i = 0; i < selectedUrls.length; i++) {
        const currentNum = i + 1;
        const percentage = Math.round((i / totalVideos) * 100);
        const sizeStr = downloadedSize > 0 ? ` | ${formatFileSize(downloadedSize)} downloaded` : '';
        const statusMsg = `📥 Downloading ${currentNum}/${totalVideos} (${percentage}%)${sizeStr}...`;
        
        console.log('Setting status:', statusMsg);
        setDownloadStatus(() => statusMsg);
        
        // Delay before starting download to show status
        await new Promise(resolve => setTimeout(resolve, 300));
        
        try {
          const response = await axios.post(`${API_BASE}/api/download`, {
            url: selectedUrls[i],
            quality: String(selectedFormat?.quality || selectedFormat?.resolution || 'best'),
            format_id: selectedFormat?.format_id ? String(selectedFormat.format_id) : null
          });
          
          const filesize = response.data.filesize || 0;
          downloadedSize += filesize;
          setTotalDownloadedSize(downloadedSize);
          
          results.push({
            success: true,
            url: selectedUrls[i],
            file_id: response.data.file_id,
            filename: response.data.filename,
            download_url: response.data.download_url,
            title: response.data.filename,
            ext: response.data.ext,
            filesize: filesize
          });
          
          // Update progress after successful download
          const completedPercentage = Math.round(((i + 1) / totalVideos) * 100);
          const statusMsg = `✓ Downloaded ${currentNum}/${totalVideos} (${completedPercentage}%) | ${formatFileSize(downloadedSize)} total`;
          
          console.log('Download complete, updating status:', statusMsg);
          
          // Force state updates with functional setters
          setDownloadStatus(prev => statusMsg);
          setDownloadProgress(prev => [...results]);
          setTotalDownloadedSize(prev => downloadedSize);
          
          // Longer delay to ensure UI updates are visible
          await new Promise(resolve => setTimeout(resolve, 500));
        } catch (err) {
          results.push({
            success: false,
            url: selectedUrls[i],
            error: err.response?.data?.detail || 'Download failed'
          });
          setDownloadProgress([...results]);
        }
      }
      
      // Create ZIP file
      setDownloadStatus('📦 Creating ZIP file...');
      const successfulDownloads = results.filter(r => r.success);
      
      if (successfulDownloads.length > 0) {
        const zipResponse = await axios.post(`${API_BASE}/api/create-zip`, {
          file_ids: successfulDownloads.map(r => r.file_id)
        });
        
        if (zipResponse.data.zip_url) {
          setZipUrl(`${API_BASE}${zipResponse.data.zip_url}`);
        }
      }
      
      setDownloadStatus(`✅ Complete! ${successfulDownloads.length}/${totalVideos} successful | ${formatFileSize(downloadedSize)} total`);
    } catch (err) {
      const errorMsg = err.response?.data?.detail;
      setError(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg) || 'Failed to download videos');
      setDownloadStatus('');
    } finally {
      setLoading(false);
    }
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return 'Unknown size';
    const mb = bytes / (1024 * 1024);
    return `${mb.toFixed(2)} MB`;
  };

  const formatDuration = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="App">
      <div className="container">
        <h1>YouTube Downloader</h1>
        <p className="subtitle">Download YouTube videos in various qualities</p>

        <div className="input-section">
          <input
            type="text"
            placeholder="Enter YouTube URL..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && fetchVideoInfo()}
            className="url-input"
          />
          <button 
            onClick={fetchVideoInfo} 
            disabled={loading}
            className="fetch-btn"
          >
            {loading ? 'Loading...' : 'Get Video Info'}
          </button>
        </div>

        {error && <div className="error">{error}</div>}
        {downloadStatus && (
          <div className="success">
            <div style={{ fontSize: '20px', fontWeight: 'bold', marginBottom: '10px' }}>
              {downloadStatus}
            </div>
            {loading && downloadProgress.length > 0 && playlistInfo && (
              <div className="progress-bar-container" style={{ marginTop: '10px' }}>
                <div 
                  className="progress-bar-fill" 
                  style={{ 
                    width: `${Math.round((downloadProgress.length / playlistInfo.videos.filter(v => selectedVideos.has(v.id)).length) * 100)}%` 
                  }}
                />
              </div>
            )}
          </div>
        )}

        {playlistInfo && playlistInfo.is_playlist && (
          <div className="playlist-info">
            <div className="playlist-header">
              <h2>📋 {playlistInfo.title}</h2>
              <p>{playlistInfo.video_count} videos</p>
            </div>

            <div className="selection-controls">
              <button onClick={selectAllVideos} className="control-btn">
                ✓ Select All
              </button>
              <button onClick={deselectAllVideos} className="control-btn">
                ✗ Deselect All
              </button>
              <span className="selected-count">
                {selectedVideos.size} selected
              </span>
            </div>

            {videoInfo && videoInfo.formats && (
              <div className="quality-section">
                <h3>Select Quality (applies to all videos):</h3>
                <div className="quality-grid">
                  {videoInfo.formats.map((format, index) => (
                    <div
                      key={index}
                      className={`quality-option ${selectedFormat === format ? 'selected' : ''}`}
                      onClick={() => setSelectedFormat(format)}
                    >
                      <div className="quality-label">
                        {format.resolution}
                        {format.fps && ` (${format.fps}fps)`}
                      </div>
                      <div className="quality-info">
                        {format.ext} • {formatFileSize(format.filesize)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="playlist-videos">
              {playlistInfo.videos.map((video) => (
                <div
                  key={video.id}
                  className={`playlist-video-item ${selectedVideos.has(video.id) ? 'selected' : ''}`}
                  onClick={() => toggleVideoSelection(video.id)}
                >
                  <input
                    type="checkbox"
                    checked={selectedVideos.has(video.id)}
                    onChange={() => {}}
                    className="video-checkbox"
                  />
                  {video.thumbnail && (
                    <img src={video.thumbnail} alt={video.title} className="video-thumb" />
                  )}
                  <div className="video-info-text">
                    <h4>{video.title}</h4>
                    <p>{formatDuration(video.duration)}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="download-section">
              <button
                onClick={handleBatchDownload}
                disabled={loading || selectedVideos.size === 0}
                className="download-btn batch"
              >
                📦 Download Selected ({selectedVideos.size})
              </button>
            </div>

            {downloadProgress.length > 0 && (
              <div className="download-progress">
                <h3>Download Results:</h3>
                {downloadProgress.map((result, index) => (
                  <div key={index} className={`progress-item ${result.success ? 'success' : 'failed'}`}>
                    <span>{result.title || result.url}</span>
                    <span>{result.success ? '✓ Success' : '✗ ' + result.error}</span>
                  </div>
                ))}
                
                {zipUrl && (
                  <div className="zip-download-section">
                    <a 
                      href={zipUrl} 
                      download="videos.zip"
                      className="download-btn zip-btn"
                    >
                      📥 Download All as ZIP
                    </a>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {videoInfo && !playlistInfo && (
          <div className="video-info">
            <div className="video-header">
              {videoInfo.thumbnail && (
                <img 
                  src={videoInfo.thumbnail} 
                  alt={videoInfo.title}
                  className="thumbnail"
                />
              )}
              <div className="video-details">
                <h2>{videoInfo.title}</h2>
                <p>Duration: {formatDuration(videoInfo.duration)}</p>
              </div>
            </div>

            <div className="quality-section">
              <h3>Select Quality:</h3>
              <div className="quality-grid">
                {videoInfo.formats.map((format, index) => (
                  <div
                    key={index}
                    className={`quality-option ${selectedFormat === format ? 'selected' : ''}`}
                    onClick={() => setSelectedFormat(format)}
                  >
                    <div className="quality-label">
                      {format.resolution}
                      {format.fps && ` (${format.fps}fps)`}
                    </div>
                    <div className="quality-info">
                      {format.ext} • {formatFileSize(format.filesize)}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="download-section">
              <button 
                onClick={handleDirectDownload}
                disabled={loading || !selectedFormat}
                className="download-btn direct"
              >
                🔗 Direct Download Link
              </button>
              <button 
                onClick={handleServerDownload}
                disabled={loading || !selectedFormat}
                className="download-btn server"
              >
                💾 Download via Server
              </button>
            </div>

            <div className="info-box">
              <p><strong>Direct Download:</strong> Opens the video stream URL directly (faster, no server storage)</p>
              <p><strong>Server Download:</strong> Downloads to server first, then to your device (more reliable)</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
