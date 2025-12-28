/** Video information display component */
import React from 'react';
import { formatFileSize, formatDuration } from '../../utils/formatters';

const VideoInfo = ({ videoInfo, selectedFormat, onFormatSelect }) => {
  if (!videoInfo) return null;

  // Debug: Log formats received
  console.log('VideoInfo: Received formats:', videoInfo.formats?.length || 0);
  console.log('VideoInfo: Formats data:', videoInfo.formats);

  return (
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
        {videoInfo.formats && videoInfo.formats.length === 0 && (
          <p style={{color: 'red'}}>⚠️ No formats available</p>
        )}
        {videoInfo.formats && videoInfo.formats.length === 1 && (
          <p style={{color: 'orange'}}>⚠️ Only 1 format found (expected more)</p>
        )}
        <div className="quality-grid">
          {videoInfo.formats && videoInfo.formats.map((format, index) => (
            <div
              key={index}
              className={`quality-option ${selectedFormat === format ? 'selected' : ''}`}
              onClick={() => onFormatSelect(format)}
            >
              <div className="quality-label">
                {format.resolution}
                {format.fps && ` (${format.fps}fps)`}
              </div>
              <div className="quality-info">
                {format.ext} • {format.filesize && format.filesize > 0 ? formatFileSize(format.filesize) : 'Size unknown'}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default VideoInfo;

