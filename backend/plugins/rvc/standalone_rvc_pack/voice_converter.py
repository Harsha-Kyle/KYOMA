import os
import sys
import traceback
import logging
import numpy as np
import soundfile as sf
import torch
from io import BytesIO
from pathlib import Path

# Add current directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from infer.lib.audio import load_audio, wav2
from infer.lib.infer_pack.models import (
    SynthesizerTrnMs256NSFsid,
    SynthesizerTrnMs256NSFsid_nono,
    SynthesizerTrnMs768NSFsid,
    SynthesizerTrnMs768NSFsid_nono,
)
from infer.modules.vc.pipeline import Pipeline
from infer.modules.vc.utils import load_hubert
from config import StandaloneConfig


class StandaloneVoiceConverter:
    """Standalone voice converter that doesn't require the full RVC environment"""
    
    def __init__(self, config=None):
        self.config = config or StandaloneConfig()
        self.n_spk = None
        self.tgt_sr = None
        self.net_g = None
        self.pipeline = None
        self.cpt = None
        self.version = None
        self.if_f0 = None
        self.hubert_model = None
        
        # Set up paths
        self.assets_dir = os.path.join(current_dir, "assets")
        self.hubert_path = os.path.join(self.assets_dir, "hubert", "hubert_base.pt")
        self.rmvpe_path = os.path.join(self.assets_dir, "rmvpe", "rmvpe.pt")
        
    def load_model(self, model_path, index_path=None):
        """Load RVC model from path"""
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file not found: {model_path}")
            
        logger.info(f"Loading model: {model_path}")
        
        # Load checkpoint
        self.cpt = torch.load(model_path, map_location="cpu")
        self.tgt_sr = self.cpt["config"][-1]
        self.cpt["config"][-3] = self.cpt["weight"]["emb_g.weight"].shape[0]  # n_spk
        self.if_f0 = self.cpt.get("f0", 1)
        self.version = self.cpt.get("version", "v1")
        
        # Initialize model based on version and f0
        synthesizer_class = {
            ("v1", 1): SynthesizerTrnMs256NSFsid,
            ("v1", 0): SynthesizerTrnMs256NSFsid_nono,
            ("v2", 1): SynthesizerTrnMs768NSFsid,
            ("v2", 0): SynthesizerTrnMs768NSFsid_nono,
        }
        
        self.net_g = synthesizer_class.get(
            (self.version, self.if_f0), SynthesizerTrnMs256NSFsid
        )(*self.cpt["config"], is_half=self.config.is_half)
        
        # Remove encoder q layer and load weights
        del self.net_g.enc_q
        self.net_g.load_state_dict(self.cpt["weight"], strict=False)
        self.net_g.eval().to(self.config.device)
        
        if self.config.is_half:
            self.net_g = self.net_g.half()
        else:
            self.net_g = self.net_g.float()
            
        # Initialize pipeline
        self.pipeline = Pipeline(self.tgt_sr, self.config)
        
        logger.info(f"Model loaded successfully. Version: {self.version}, F0: {self.if_f0}")
        
    def convert_voice(
        self,
        input_audio_path,
        output_path=None,
        speaker_id=0,
        f0_up_key=0,
        f0_method="rmvpe",
        index_path=None,
        index_rate=0.75,
        filter_radius=3,
        resample_sr=0,
        rms_mix_rate=0.25,
        protect=0.33,
        f0_file=None
    ):
        """
        Convert voice using the loaded model
        
        Args:
            input_audio_path: Path to input audio file
            output_path: Path to save output audio (optional)
            speaker_id: Speaker ID (usually 0 for single speaker models)
            f0_up_key: Pitch shift in semitones
            f0_method: F0 extraction method ("rmvpe", "pm", "harvest", "crepe")
            index_path: Path to index file for feature matching
            index_rate: Feature matching strength (0-1)
            filter_radius: Median filter radius for F0
            resample_sr: Output sample rate (0 = use model's sample rate)
            rms_mix_rate: RMS mixing ratio
            protect: Protection for consonants and breath sounds
            f0_file: Custom F0 curve file
            
        Returns:
            tuple: (info_message, (sample_rate, audio_array))
        """
        if self.net_g is None:
            return "No model loaded. Please load a model first.", (None, None)
            
        if not os.path.exists(input_audio_path):
            return f"Input file not found: {input_audio_path}", (None, None)
            
        try:
            # Load and preprocess audio
            audio = load_audio(input_audio_path, 16000)
            audio_max = np.abs(audio).max() / 0.95
            if audio_max > 1:
                audio /= audio_max
                
            times = [0, 0, 0]
            
            # Load Hubert model if not already loaded
            if self.hubert_model is None:
                self.hubert_model = load_hubert(self.config)
                
            # Process index file path
            if index_path and os.path.exists(index_path):
                file_index = index_path.strip(" ").strip('"').strip("\n").strip('"').strip(" ")
                file_index = file_index.replace("trained", "added")
            else:
                file_index = ""
                
            # Run voice conversion pipeline
            audio_opt = self.pipeline.pipeline(
                self.hubert_model,
                self.net_g,
                speaker_id,
                audio,
                input_audio_path,
                times,
                f0_up_key,
                f0_method,
                file_index,
                index_rate,
                self.if_f0,
                filter_radius,
                self.tgt_sr,
                resample_sr,
                rms_mix_rate,
                self.version,
                protect,
                f0_file,
            )
            
            # Determine output sample rate
            if self.tgt_sr != resample_sr >= 16000:
                tgt_sr = resample_sr
            else:
                tgt_sr = self.tgt_sr
                
            # Save output if path provided
            if output_path:
                sf.write(output_path, audio_opt, tgt_sr)
                logger.info(f"Output saved to: {output_path}")
                
            index_info = (
                f"Index: {file_index}" if os.path.exists(file_index) else "Index not used"
            )
            
            info_message = (
                f"Conversion successful.\n{index_info}\n"
                f"Time: npy: {times[0]:.2f}s, f0: {times[1]:.2f}s, infer: {times[2]:.2f}s"
            )
            
            return info_message, (tgt_sr, audio_opt)
            
        except Exception as e:
            error_info = traceback.format_exc()
            logger.error(f"Conversion failed: {error_info}")
            return f"Conversion failed: {str(e)}", (None, None)
    
    def batch_convert(
        self,
        input_dir,
        output_dir,
        speaker_id=0,
        f0_up_key=0,
        f0_method="rmvpe",
        index_path=None,
        index_rate=0.75,
        filter_radius=3,
        resample_sr=0,
        rms_mix_rate=0.25,
        protect=0.33,
        output_format="wav"
    ):
        """
        Batch convert all audio files in a directory
        
        Args:
            input_dir: Directory containing input audio files
            output_dir: Directory to save converted files
            Other args: Same as convert_voice method
            output_format: Output format ("wav", "flac", "mp3", "m4a")
            
        Returns:
            Generator yielding progress messages
        """
        if not os.path.exists(input_dir):
            yield f"Input directory not found: {input_dir}"
            return
            
        os.makedirs(output_dir, exist_ok=True)
        
        # Get all audio files
        audio_extensions = {'.wav', '.mp3', '.flac', '.m4a', '.aac', '.ogg'}
        audio_files = []
        
        for file in os.listdir(input_dir):
            if any(file.lower().endswith(ext) for ext in audio_extensions):
                audio_files.append(os.path.join(input_dir, file))
                
        if not audio_files:
            yield "No audio files found in input directory"
            return
            
        yield f"Found {len(audio_files)} audio files to process"
        
        for i, audio_file in enumerate(audio_files):
            filename = os.path.splitext(os.path.basename(audio_file))[0]
            output_file = os.path.join(output_dir, f"{filename}.{output_format}")
            
            yield f"Processing {i+1}/{len(audio_files)}: {filename}"
            
            info, (sr, audio_opt) = self.convert_voice(
                audio_file,
                speaker_id=speaker_id,
                f0_up_key=f0_up_key,
                f0_method=f0_method,
                index_path=index_path,
                index_rate=index_rate,
                filter_radius=filter_radius,
                resample_sr=resample_sr,
                rms_mix_rate=rms_mix_rate,
                protect=protect
            )
            
            if sr is not None and audio_opt is not None:
                try:
                    if output_format in ["wav", "flac"]:
                        sf.write(output_file, audio_opt, sr)
                    else:
                        # For other formats, use wav2 function
                        with BytesIO() as wavf:
                            sf.write(wavf, audio_opt, sr, format="wav")
                            wavf.seek(0, 0)
                            with open(output_file, "wb") as outf:
                                wav2(wavf, outf, output_format)
                    yield f"✓ {filename} -> {info}"
                except Exception as e:
                    yield f"✗ {filename} -> Error: {str(e)}"
            else:
                yield f"✗ {filename} -> {info}"
                
        yield "Batch conversion completed!"
        

def main():
    """Example usage of the standalone voice converter"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Standalone RVC Voice Converter")
    parser.add_argument("--model", required=True, help="Path to RVC model file (.pth)")
    parser.add_argument("--input", required=True, help="Input audio file or directory")
    parser.add_argument("--output", help="Output file or directory")
    parser.add_argument("--index", help="Path to index file")
    parser.add_argument("--f0-method", default="rmvpe", choices=["rmvpe", "pm", "harvest", "crepe"],
                        help="F0 extraction method")
    parser.add_argument("--f0-up-key", type=int, default=0, help="Pitch shift in semitones")
    parser.add_argument("--index-rate", type=float, default=0.75, help="Feature matching strength")
    parser.add_argument("--batch", action="store_true", help="Batch process directory")
    parser.add_argument("--device", help="Device to use (cuda:0, cpu, etc.)")
    parser.add_argument("--format", default="wav", choices=["wav", "flac", "mp3", "m4a"],
                        help="Output format for batch processing")
    
    args = parser.parse_args()
    
    # Initialize converter
    config = StandaloneConfig(device=args.device)
    converter = StandaloneVoiceConverter(config)
    
    # Load model
    converter.load_model(args.model, args.index)
    
    if args.batch:
        # Batch processing
        output_dir = args.output or "output"
        print(f"Starting batch conversion from {args.input} to {output_dir}")
        
        for message in converter.batch_convert(
            args.input, 
            output_dir,
            f0_up_key=args.f0_up_key,
            f0_method=args.f0_method,
            index_path=args.index,
            index_rate=args.index_rate,
            output_format=args.format
        ):
            print(message)
    else:
        # Single file processing
        output_path = args.output or f"output_{os.path.basename(args.input)}"
        print(f"Converting {args.input} to {output_path}")
        
        info, (sr, audio) = converter.convert_voice(
            args.input,
            output_path,
            f0_up_key=args.f0_up_key,
            f0_method=args.f0_method,
            index_path=args.index,
            index_rate=args.index_rate
        )
        
        print(info)


if __name__ == "__main__":
    main() 