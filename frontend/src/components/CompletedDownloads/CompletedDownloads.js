/** Completed downloads list component */
import React from 'react';
import { formatFileSize } from '../../utils/formatters';
import { getDownloadFileUrl } from '../../services/api';

const CompletedDownloads = ({ downloads }) => {
  if (!downloads || downloads.length === 0) return null;

  return (
    <div className="completed-downloads">
      <h3>📁 Downloaded Files</h3>
      <div className="downloads-list">
        {downloads.map((download, index) => (
          <div key={index} className="download-item">
            <div className="download-info">
              <div className="download-filename">{download.filename}</div>
              <div className="download-meta">
                {formatFileSize(download.filesize)} • {download.timestamp}
              </div>
            </div>
            <a
              href={download.downloadUrl}
              download={download.filename}
              className="download-item-btn"
            >
              ⬇️ Download
            </a>
          </div>
        ))}
      </div>
    </div>
  );
};

export default CompletedDownloads;


