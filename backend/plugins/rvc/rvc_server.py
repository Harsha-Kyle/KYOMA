import os
import sys
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

import logging
import json
from typing import Optional, List, Dict
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
import edge_tts
from edge_tts_voices import SUPPORTED_VOICES
import asyncio
import soundfile as sf
import tempfile
import requests
import zipfile
from urllib.parse import urlparse, unquote
import shutil

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Get current directory
current_dir = os.path.dirname(os.path.abspath(__file__))
models_dir = os.path.join(current_dir, "models")
output_dir = os.path.join(current_dir, "output")

# Create output directory if it doesn't exist
os.makedirs(output_dir, exist_ok=True)

# Initialize converter
from standalone_rvc_pack.voice_converter import StandaloneVoiceConverter
from standalone_rvc_pack.config import StandaloneConfig

config = StandaloneConfig()
converter = StandaloneVoiceConverter(config)
current_model = None

class TTSRequest(BaseModel):
    text: str
    voice: str = "en-US-AriaNeural"
    pitch: str = "+0Hz"
    rate: str = "+0%"
    use_rvc: bool = False  # New parameter to explicitly control RVC usage
    model_name: Optional[str] = None  # Model name is now optional regardless of RVC usage
    f0_up_key: int = 0
    f0_method: str = "rmvpe"
    index_rate: float = 0.75
    filter_radius: int = 3
    resample_sr: int = 0
    rms_mix_rate: float = 0.25
    protect: float = 0.33

class ModelDownloadRequest(BaseModel):
    url: HttpUrl

def get_available_models() -> List[Dict[str, str]]:
    """Get list of available RVC models"""
    models = []
    if os.path.exists(models_dir):
        for model_name in os.listdir(models_dir):
            model_dir = os.path.join(models_dir, model_name)
            if os.path.isdir(model_dir):
                # Look for .pth and .index files
                pth_file = None
                index_file = None
                for file in os.listdir(model_dir):
                    if file.endswith('.pth'):
                        pth_file = os.path.join(model_dir, file)
                    elif file.endswith('.index'):
                        index_file = os.path.join(model_dir, file)
                
                if pth_file:  # Only add if we found the .pth file
                    models.append({
                        "name": model_name,
                        "model_path": pth_file,
                        "index_path": index_file
                    })
    return models

def get_available_edge_models() -> List[Dict[str, str]]:
    return list(SUPPORTED_VOICES.keys())

@app.get("/status")
async def get_status():
    """Get RVC server status"""
    return JSONResponse(content={"running": True})

@app.get("/models")
async def list_models():
    """List available RVC models"""
    try:
        models = get_available_models()
        return JSONResponse(content={
            "models": models,
            "current_model": current_model
        })
    except Exception as e:
        logger.error(f"Error listing models: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/edge-models")
async def list_edge_models():
    """List available Edge TTS models"""
    try:
        models = get_available_edge_models()
        return JSONResponse(content={
            "models": models
        })
    except Exception as e:
        logger.error(f"Error listing Edge TTS models: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/load_model/{model_name}")
async def load_model(model_name: str):
    """Load an RVC model by name"""
    try:
        models = get_available_models()
        model_info = next((m for m in models if m["name"] == model_name), None)
        
        if not model_info:
            raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")
            
        # Load the model
        converter.load_model(model_info["model_path"], model_info["index_path"])
        global current_model
        current_model = model_name
        
        return JSONResponse(content={
            "message": f"Model '{model_name}' loaded successfully",
            "model_info": model_info
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/convert")
async def convert_text(request: TTSRequest):
    """Convert text to speech using Edge TTS and optionally RVC"""
    try:
        # Generate filenames
        tts_output = os.path.join(output_dir, "tts_output.wav")
        rvc_output = os.path.join(output_dir, "rvc_output.wav")
        
        # Generate speech with Edge TTS
        communicate = edge_tts.Communicate(
            request.text, 
            request.voice
        )
        
        # Save TTS output
        await communicate.save(tts_output)
        
        # If RVC is not requested, return TTS output directly
        if not request.use_rvc:
            return FileResponse(
                tts_output,
                media_type="audio/wav",
                filename="output.wav"
            )
            
        # Validate RVC parameters
        if not request.model_name:
            raise HTTPException(status_code=400, detail="model_name is required when use_rvc is True")
            
        # Load RVC model if needed
        if current_model != request.model_name:
            await load_model(request.model_name)
            
        # Convert voice with RVC
        info, audio_data = converter.convert_voice(
            tts_output,
            f0_up_key=request.f0_up_key,
            f0_method=request.f0_method,
            index_rate=request.index_rate,
            filter_radius=request.filter_radius,
            resample_sr=request.resample_sr,
            rms_mix_rate=request.rms_mix_rate,
            protect=request.protect
        )
        
        if audio_data[0] is None:
            raise HTTPException(status_code=500, detail=info)
            
        # Save RVC output
        sf.write(rvc_output, audio_data[1], audio_data[0])
        
        return FileResponse(
            rvc_output,
            media_type="audio/wav",
            filename="output.wav"
        )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error converting voice: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/download_model")
async def download_model(request: ModelDownloadRequest):
    """Download and setup an RVC model from a URL"""
    try:
        # Extract filename from URL
        parsed_url = urlparse(str(request.url))
        filename = unquote(os.path.basename(parsed_url.path))
        if not filename.endswith('.zip'):
            raise HTTPException(status_code=400, detail="URL must point to a zip file")
            
        # Remove .zip extension to get model name
        model_name = os.path.splitext(filename)[0]
        model_dir = os.path.join(models_dir, model_name)
        
        # Create temporary directory for download
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, filename)
            
            # Download the file
            logger.info(f"Downloading model from {request.url}")
            response = requests.get(str(request.url), stream=True)
            response.raise_for_status()
            
            # Save to temporary file
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
            # Verify it's a valid zip file
            if not zipfile.is_zipfile(zip_path):
                raise HTTPException(status_code=400, detail="Downloaded file is not a valid zip file")
                
            # Remove existing model directory if it exists
            if os.path.exists(model_dir):
                shutil.rmtree(model_dir)
                
            # Create model directory
            os.makedirs(model_dir)
            
            # Extract zip file
            logger.info(f"Extracting model to {model_dir}")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(model_dir)
                
            # Verify required files exist
            has_pth = False
            has_index = False
            for root, _, files in os.walk(model_dir):
                for file in files:
                    if file.endswith('.pth'):
                        has_pth = True
                    elif file.endswith('.index'):
                        has_index = True
                    if has_pth and has_index:
                        break
                        
            if not has_pth:
                shutil.rmtree(model_dir)
                raise HTTPException(status_code=400, detail="No .pth file found in zip")
                
            return JSONResponse(content={
                "message": f"Model '{model_name}' downloaded and extracted successfully",
                "model_name": model_name,
                "has_index": has_index
            })
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading model: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to download model: {str(e)}")
    except zipfile.BadZipFile:
        logger.error("Invalid zip file")
        raise HTTPException(status_code=400, detail="Invalid zip file")
    except Exception as e:
        logger.error(f"Error processing model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8001)
    
