import httpx
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from typing import Optional, Callable
from .LAV_logger import logger

async def forward_request(request: Request, from_path: str, to_url: str) -> Response:
    """
    Forward a request from one path to another URL.
    
    Args:
        request (Request): The incoming FastAPI request
        from_path (str): The path prefix to strip (e.g. "/api/rvc")
        to_url (str): The base URL to forward to (e.g. "http://localhost:8001")
        
    Returns:
        Response: The response from the forwarded request
    """
    # Strip prefix and create target URL
    path = request.url.path.replace(from_path, "", 1)
    target_url = f"{to_url}{path}"
    
    async with httpx.AsyncClient() as client:
        try:
            # Forward the request with same method, body, and headers
            body = await request.body()
            headers = {k: v for k, v in request.headers.items() 
                     if k.lower() not in ["host", "content-length"]}
            
            response = await client.request(
                method=request.method,
                url=target_url,
                content=body,
                headers=headers,
                params=request.query_params
            )
            
            return Response(
                content=response.content,
                status_code=response.status_code,
                media_type=response.headers.get("content-type")
            )
        except Exception as e:
            logger.error(f"Error forwarding request: {e}")
            return JSONResponse(
                status_code=502,
                content={"detail": "Target server not available"}
            )

def create_proxy_middleware(from_path: str, to_port: int) -> Callable:
    """
    Create a FastAPI middleware function that forwards requests from one path to another port.
    
    Args:
        from_path (str): The path prefix to forward from (e.g. "/api/rvc")
        to_port (int): The port to forward to
        
    Returns:
        Callable: A middleware function that can be used with FastAPI
    """
    async def proxy_middleware(request: Request, call_next):
        if request.url.path.startswith(from_path):
            return await forward_request(
                request=request,
                from_path=from_path,
                to_url=f"http://localhost:{to_port}"
            )
        return await call_next(request)
        
    return proxy_middleware 