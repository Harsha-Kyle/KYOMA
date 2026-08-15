#!/usr/bin/env python3
"""
Example usage of the Standalone RVC Voice Converter
"""

import os
import sys
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from voice_converter import StandaloneVoiceConverter, StandaloneConfig

def main():

    current_module_directory = os.path.dirname(__file__)
    # Example paths - modify these for your setup
    model_path = os.path.join(current_module_directory, "assets", "rvc_model_dir", "qiqi.pth")
    input_audio = os.path.join(current_module_directory, "assets", "edgetts_output.wav") 
    output_audio = os.path.join(current_module_directory, "assets", "yes_there_is_output.wav")
    index_path = os.path.join(current_module_directory, "assets", "rvc_index_dir", "qiqi.index")  # Optional
    
    print("Initializing Standalone RVC Voice Converter...")
    
    # Create configuration (auto-detects GPU/CPU)
    config = StandaloneConfig()
    print(f"Using device: {config.device}")
    print(f"Half precision: {config.is_half}")
    
    # Initialize converter
    converter = StandaloneVoiceConverter(config)
    
    # Check if model exists
    if not os.path.exists(model_path):
        print(f"Error: Model file not found at {model_path}")
        print("Please update the model_path variable with your RVC model file")
        return
    
    # Load model
    print(f"Loading model: {model_path}")
    try:
        converter.load_model(model_path)
        print("Model loaded successfully!")
    except Exception as e:
        print(f"Error loading model: {e}")
        return
    
    # Check if input audio exists
    if not os.path.exists(input_audio):
        print(f"Error: Input audio not found at {input_audio}")
        print("Please update the input_audio variable with your input file")
        return
    
    # Convert voice
    print(f"Converting: {input_audio} -> {output_audio}")
    
    info, (sample_rate, audio_data) = converter.convert_voice(
        input_audio_path=input_audio,
        output_path=output_audio,
        speaker_id=0,
        f0_up_key=0,  # No pitch change
        f0_method="rmvpe",  # Best quality method
        index_path=index_path if os.path.exists(index_path) else None,
        index_rate=0.75,  # Feature matching strength
        filter_radius=3,  # Median filter for F0
        resample_sr=0,  # Use model's sample rate
        rms_mix_rate=0.25,  # Volume envelope mixing
        protect=0.33  # Protect consonants and breath sounds
    )
    
    print("\n" + "="*50)
    print("CONVERSION RESULT:")
    print("="*50)
    print(info)
    
    if sample_rate is not None and audio_data is not None:
        print(f"\nOutput saved to: {output_audio}")
        print(f"Sample rate: {sample_rate} Hz")
        print(f"Audio length: {len(audio_data)/sample_rate:.2f} seconds")
    else:
        print("\nConversion failed!")

def batch_example():
    """Example of batch processing"""
    model_path = "path/to/your/model.pth"
    input_dir = "input_folder"
    output_dir = "output_folder" 
    
    config = StandaloneConfig()
    converter = StandaloneVoiceConverter(config)
    
    if not os.path.exists(model_path):
        print(f"Model not found: {model_path}")
        return
        
    converter.load_model(model_path)
    
    print(f"Batch converting from {input_dir} to {output_dir}")
    
    for progress_message in converter.batch_convert(
        input_dir=input_dir,
        output_dir=output_dir,
        f0_up_key=0,
        f0_method="rmvpe",
        output_format="wav"
    ):
        print(progress_message)

if __name__ == "__main__":
    # Run single file example
    main()
    
    # Uncomment to run batch example instead
    # batch_example() 

    # to run this file: python -m services.TTS.standalone_rvc.example