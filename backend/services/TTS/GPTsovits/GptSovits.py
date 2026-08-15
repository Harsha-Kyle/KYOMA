from io import BytesIO
import os
import shutil
import subprocess
import sys
from typing import Generator
import wave
import numpy as np
import soundfile as sf
from services.lib.LAV_logger import logger

base_dir = os.path.dirname(__file__)
sys.path.insert(0, base_dir)
sys.path.insert(0, os.path.join(base_dir, "GPT_SoVITS"))

# Import GPT_SoVITS modules using the package namespace
from services.TTS.GPTsovits.GPT_SoVITS.TTS_infer_pack.TTS import TTS as TTS_gptsovits, TTS_Config
from services.TTS.GPTsovits.GPT_SoVITS.TTS_infer_pack.text_segmentation_method import get_method_names as get_cut_method_names

current_module_directory = os.path.dirname(__file__)
cut_method_names = get_cut_method_names()

class GptSovits():
    def __init__(self):
        config_path = os.path.join(current_module_directory, "GPT_SoVITS", "configs", "tts_infer.yaml")
        self.tts_config = TTS_Config(config_path)
        try:
            self.tts_pipeline = TTS_gptsovits(self.tts_config)
            self.tts_available = True
        except Exception as e:
            logger.error(f"Failed to initialize GPT-SoVITS: {e}")
            logger.warning("GPT-SoVITS pretrained models may be missing. TTS will be disabled until weights are provided.")
            self.tts_pipeline = None
            self.tts_available = False
        
        # Initialize empty state
        self.voice_files = {}
        self.prompt_texts = {}
        self.prompt_langs = {}
        self.current_voice = None
        self.ref_audio_path = None
        self.prompt_text = None
        self.prompt_lang = None
        
        # Update voice files and try to set default voice
        self._update_voice_files()
        if self.voice_files:  # Only set if we have any voices
            self.current_voice = "leaf" if "leaf" in self.voice_files else next(iter(self.voice_files))
            self.ref_audio_path = os.path.join(current_module_directory, "models", self.current_voice, self.voice_files[self.current_voice])
            self.prompt_text = self.prompt_texts[self.current_voice]
            self.prompt_lang = self.prompt_langs[self.current_voice]

    def _update_voice_files(self):
        """Update voice files and prompt texts from the models directory"""
        models_dir = os.path.join(current_module_directory, "models")
        if not os.path.exists(models_dir):
            return

        # Rebuild state from filesystem
        new_voice_files = {}
        new_prompt_texts = {}
        new_prompt_langs = {}

        for voice_dir in os.listdir(models_dir):
            voice_path = os.path.join(models_dir, voice_dir)
            if os.path.isdir(voice_path):
                # Look for metadata.json
                metadata_path = os.path.join(voice_path, "metadata.json")
                if os.path.exists(metadata_path):
                    try:
                        import json
                        with open(metadata_path, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                            
                        audio_file = metadata.get('audio_file')
                        if audio_file and os.path.exists(os.path.join(voice_path, audio_file)):
                            new_voice_files[voice_dir] = audio_file
                            new_prompt_texts[voice_dir] = metadata.get('reference_text', '')
                            new_prompt_langs[voice_dir] = metadata.get('language', 'en')
                    except Exception as e:
                        logger.error(f"Error reading metadata for voice {voice_dir}: {e}")
                        continue

        # Update state
        self.voice_files = new_voice_files
        self.prompt_texts = new_prompt_texts
        self.prompt_langs = new_prompt_langs

        # Update current voice if needed
        if self.current_voice not in self.voice_files:
            # Try to use leaf, otherwise use first available voice
            self.current_voice = "leaf" if "leaf" in self.voice_files else next(iter(self.voice_files), None)
            if self.current_voice:
                self.ref_audio_path = os.path.join(models_dir, self.current_voice, self.voice_files[self.current_voice])
                self.prompt_text = self.prompt_texts[self.current_voice]
                self.prompt_lang = self.prompt_langs[self.current_voice]
            else:
                self.ref_audio_path = None
                self.prompt_text = None
                self.prompt_lang = None

    def get_available_voices(self):
        """Get list of available voices from the models directory"""
        self._update_voice_files()  # Always get the latest voice files
        return list(self.voice_files.keys())

    def change_voice(self, voice_name):
        """Change the current voice to the specified one"""
        self._update_voice_files()  # Update voice files before checking
        if voice_name not in self.voice_files:
            raise ValueError(f"Voice '{voice_name}' not found")
            
        self.current_voice = voice_name
        self.ref_audio_path = os.path.join(current_module_directory, "models", voice_name, self.voice_files[voice_name])
        self.prompt_text = self.prompt_texts[voice_name]
        self.prompt_lang = self.prompt_langs[voice_name]
        return {"message": f"Voice changed to {voice_name}"}

    def synthesize(self, text):
        self._update_voice_files()  # Update voice files before synthesis
        
        if not self.current_voice:
            raise ValueError("No voice models available. Please upload a voice model first.")
            
        if not self.ref_audio_path or not os.path.exists(self.ref_audio_path):
            raise ValueError(f"Reference audio file not found for voice '{self.current_voice}'")
        
        req = {
            "text": text,
            "text_lang": 'auto',
            "ref_audio_path": self.ref_audio_path,
            "aux_ref_audio_paths": [],
            "prompt_text": self.prompt_text,
            "prompt_lang": self.prompt_lang,
            "top_k": 5,
            "top_p": 1,
            "temperature": 1,
            "text_split_method": "cut0",
            "batch_size": int(1),
            "batch_threshold": float(0.75),
            "speed_factor": float(1.0),
            "split_bucket": True,
            "fragment_interval": 0.3,
            "seed": -1,
            "media_type": "wav",
            "streaming_mode": False,
            "parallel_infer": True,
            "repetition_penalty": float(1.35),
            "sample_steps": int(32),
            "super_sampling": False
        }
        
        streaming_mode = req.get("streaming_mode", False)
        return_fragment = req.get("return_fragment", False)
        media_type = req.get("media_type", "wav")

        check_res = self.check_params(req)
        if check_res is not None:
            return check_res

        if streaming_mode or return_fragment:
            req["return_fragment"] = True
            
        try:
            if not self.tts_available or self.tts_pipeline is None:
                return {"message": "TTS engine is not available (likely missing weights)"}
                
            tts_generator = self.tts_pipeline.run(req)
            
            if streaming_mode:
                def streaming_generator(tts_generator: Generator, media_type: str):
                    if_frist_chunk = True
                    for sr, chunk in tts_generator:
                        if if_frist_chunk and media_type == "wav":
                            yield wave_header_chunk(sample_rate=sr)
                            media_type = "raw"
                            if_frist_chunk = False
                        yield pack_audio(BytesIO(), chunk, sr, media_type).getvalue()
                return streaming_generator(tts_generator, media_type)
        
            else:
                sr, audio_data = next(tts_generator)
                audio_data = pack_audio(BytesIO(), audio_data, sr, media_type).getvalue()
                return audio_data
        except Exception as e:
            logger.error(f"Error during completion: {e}", exc_info=True)
            return {"message": f"tts failed", "Exception": str(e)}
        
    def upload_voice(self, name, reference_audio, reference_text, reference_language):
        """Upload a new voice to the models directory.
        
        Args:
            name (str): Name of the voice (will be used as directory name)
            reference_audio (bytes): Audio file data
            reference_text (str): Reference text that matches the audio
            reference_language (str): Language code for the reference text
        
        Returns:
            dict: Status message
        """
        try:
            # Create voice directory
            voice_dir = os.path.join(current_module_directory, "models", name)
            os.makedirs(voice_dir, exist_ok=True)
            
            # Save audio file with a simple name
            audio_file = "reference.wav"
            wav_path = os.path.join(voice_dir, audio_file)
            
            # Save audio file
            audio_buffer = BytesIO(reference_audio)
            
            # Convert to wav if needed using soundfile
            try:
                data, samplerate = sf.read(audio_buffer)
                sf.write(wav_path, data, samplerate)
            except Exception as e:
                # If soundfile fails, try ffmpeg conversion
                process = subprocess.Popen([
                    'ffmpeg',
                    '-i', 'pipe:0',  # Read from stdin
                    '-ar', '32000',  # Set sample rate to 32kHz
                    '-ac', '1',      # Convert to mono
                    '-f', 'wav',     # Output format
                    wav_path         # Output file
                ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                # Reset buffer position and write to ffmpeg
                audio_buffer.seek(0)
                process.communicate(input=audio_buffer.read())
                
                if process.returncode != 0:
                    raise ValueError("Failed to convert audio file to WAV format")
            
            # Create metadata.json
            metadata = {
                "reference_text": reference_text,
                "language": reference_language,
                "audio_file": audio_file
            }
            
            metadata_path = os.path.join(voice_dir, "metadata.json")
            import json
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            # Update voice files
            self._update_voice_files()
            
            return {
                "message": f"Voice '{name}' uploaded successfully",
                "voice_path": wav_path
            }
            
        except Exception as e:
            logger.error(f"Error uploading voice: {e}", exc_info=True)
            raise ValueError(f"Failed to upload voice: {str(e)}")
    
    def delete_voice(self, name):
        """Delete a voice from the models directory.
        
        Args:
            name (str): Name of the voice to delete
        
        Returns:
            dict: Status message
        """
        try:
            voice_dir = os.path.join(current_module_directory, "models", name)  
            if os.path.exists(voice_dir):
                shutil.rmtree(voice_dir)
                self._update_voice_files()
                return {"message": f"Voice '{name}' deleted successfully"}
            else:
                return {"message": f"Voice '{name}' not found"}
        except Exception as e:
            logger.error(f"Error deleting voice: {e}", exc_info=True)
            raise ValueError(f"Failed to delete voice: {str(e)}")


    def check_params(self, req: dict):
        text: str = req.get("text", "")
        text_lang: str = req.get("text_lang", "")
        ref_audio_path: str = req.get("ref_audio_path", "")
        streaming_mode: bool = req.get("streaming_mode", False)
        media_type: str = req.get("media_type", "wav")
        prompt_lang: str = req.get("prompt_lang", "")
        text_split_method: str = req.get("text_split_method", "cut5")

        if ref_audio_path in [None, ""]:
            logger.error({"message": "ref_audio_path is required"})
        if text in [None, ""]:
            logger.error({"message": "text is required"})
        if (text_lang in [None, ""]):
            logger.error({"message": "text_lang is required"})
        elif text_lang.lower() not in self.tts_config.languages:
            logger.error({"message": f"text_lang: {text_lang} is not supported in version {self.tts_config.version}"})
        if (prompt_lang in [None, ""]):
            logger.error({"message": "prompt_lang is required"})
        elif prompt_lang.lower() not in self.tts_config.languages:
            logger.error({"message": f"prompt_lang: {prompt_lang} is not supported in version {self.tts_config.version}"})
        if media_type not in ["wav", "raw", "ogg", "aac"]:
            logger.error({"message": f"media_type: {media_type} is not supported"})
        elif media_type == "ogg" and not streaming_mode:
            logger.error({"message": "ogg format is not supported in non-streaming mode"})
        
        if text_split_method not in cut_method_names:
            logger.error({"message": f"text_split_method:{text_split_method} is not supported"})

        return None

def pack_ogg(io_buffer: BytesIO, data: np.ndarray, rate: int):
    with sf.SoundFile(io_buffer, mode='w', samplerate=rate, channels=1, format='ogg') as audio_file:
        audio_file.write(data)
    return io_buffer

def pack_raw(io_buffer: BytesIO, data: np.ndarray, rate: int):
    io_buffer.write(data.tobytes())
    return io_buffer

def pack_wav(io_buffer: BytesIO, data: np.ndarray, rate: int):
    io_buffer = BytesIO()
    sf.write(io_buffer, data, rate, format='wav')
    return io_buffer

def pack_aac(io_buffer: BytesIO, data: np.ndarray, rate: int):
    process = subprocess.Popen([
        'ffmpeg',
        '-f', 's16le',  # 输入16位有符号小端整数PCM
        '-ar', str(rate),  # 设置采样率
        '-ac', '1',  # 单声道
        '-i', 'pipe:0',  # 从管道读取输入
        '-c:a', 'aac',  # 音频编码器为AAC
        '-b:a', '192k',  # 比特率
        '-vn',  # 不包含视频
        '-f', 'adts',  # 输出AAC数据流格式
        'pipe:1'  # 将输出写入管道
    ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, _ = process.communicate(input=data.tobytes())
    io_buffer.write(out)
    return io_buffer

def pack_audio(io_buffer: BytesIO, data: np.ndarray, rate: int, media_type: str):
    if media_type == "ogg":
        io_buffer = pack_ogg(io_buffer, data, rate)
    elif media_type == "aac":
        io_buffer = pack_aac(io_buffer, data, rate)
    elif media_type == "wav":
        io_buffer = pack_wav(io_buffer, data, rate)
    else:
        io_buffer = pack_raw(io_buffer, data, rate)
    io_buffer.seek(0)
    return io_buffer

def wave_header_chunk(frame_input=b"", channels=1, sample_width=2, sample_rate=32000):
    # This will create a wave header then append the frame input
    # It should be first on a streaming wav file
    # Other frames better should not have it (else you will hear some artifacts each chunk start)
    wav_buf = BytesIO()
    with wave.open(wav_buf, "wb") as vfout:
        vfout.setnchannels(channels)
        vfout.setsampwidth(sample_width)
        vfout.setframerate(sample_rate)
        vfout.writeframes(frame_input)

    wav_buf.seek(0)
    return wav_buf.read()



