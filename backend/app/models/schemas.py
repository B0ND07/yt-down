"""Pydantic models for request/response validation"""
from pydantic import BaseModel
from typing import List, Optional


class VideoURL(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    quality: Optional[str] = None
    format_id: Optional[str] = None


class BatchDownloadRequest(BaseModel):
    urls: List[str]
    quality: Optional[str] = None
    format_id: Optional[str] = None


class CreateZipRequest(BaseModel):
    file_ids: List[str]


class VideoInfo(BaseModel):
    title: str
    thumbnail: str
    duration: int
    formats: List[dict]


