import sqlite3
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from app.db.database import get_db
from app.schemas.blog import BlogCreate, BlogUpdate, BlogResponse
from app.repositories.blog_repository import BlogRepository
from app.core.logging import logger

router = APIRouter(prefix="/blogs", tags=["Blog Management"])

def get_blog_repo(conn: sqlite3.Connection = Depends(get_db)) -> BlogRepository:
    return BlogRepository(conn)

@router.post("", response_model=BlogResponse, status_code=status.HTTP_201_CREATED)
def create_blog(blog: BlogCreate, repo: BlogRepository = Depends(get_blog_repo)):
    logger.info("Creating new blog | title={}", blog.title)
    blog_id = repo.create(blog)
    return repo.get_by_id(blog_id)

@router.get("", response_model=List[BlogResponse])
def list_blogs(repo: BlogRepository = Depends(get_blog_repo)):
    return repo.list_all()

@router.get("/{blog_id}", response_model=BlogResponse)
def get_blog(blog_id: int, repo: BlogRepository = Depends(get_blog_repo)):
    blog = repo.get_by_id(blog_id)
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")
    return blog

@router.put("/{blog_id}", response_model=BlogResponse)
def update_blog(blog_id: int, blog: BlogUpdate, repo: BlogRepository = Depends(get_blog_repo)):
    logger.info("Updating blog | id={}", blog_id)
    success = repo.update(blog_id, blog)
    if not success:
        raise HTTPException(status_code=404, detail="Blog not found or no changes made")
    return repo.get_by_id(blog_id)

@router.delete("/{blog_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_blog(blog_id: int, repo: BlogRepository = Depends(get_blog_repo)):
    logger.info("Deleting blog | id={}", blog_id)
    success = repo.delete(blog_id)
    if not success:
        raise HTTPException(status_code=404, detail="Blog not found")
