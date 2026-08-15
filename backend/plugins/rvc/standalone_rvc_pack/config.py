import json
import os
import torch
from multiprocessing import cpu_count

current_dir = os.path.dirname(os.path.abspath(__file__))

class StandaloneConfig:
    """Simplified configuration class for standalone RVC"""
    
    def __init__(self, device=None, is_half=None):
        # Load JSON configurations
        self.json_config = self.load_config_json()
        
        # Device configuration
        if device is None:
            if torch.cuda.is_available():
                self.device = "cuda:0"
            else:
                self.device = "cpu"
        else:
            self.device = device
            
        # Half precision configuration
        if is_half is None:
            self.is_half = torch.cuda.is_available() and self.device.startswith("cuda")
        else:
            self.is_half = is_half
            
        # CPU count
        self.n_cpu = cpu_count()
        
        # Memory configuration based on device
        if self.is_half and torch.cuda.is_available():
            # 6G+ GPU memory configuration
            self.x_pad = 3
            self.x_query = 10
            self.x_center = 60
            self.x_max = 65
        else:
            # CPU or low memory configuration
            self.x_pad = 1
            self.x_query = 6
            self.x_center = 38
            self.x_max = 41
    
    @staticmethod
    def load_config_json():
        """Load configuration JSON files"""
        version_config_list = [
            "v1/32k.json",
            "v1/40k.json", 
            "v1/48k.json",
            "v2/48k.json",
            "v2/32k.json",
        ]
        
        d = {}
        configs_dir = os.path.join(current_dir, "configs")
        
        for config_file in version_config_list:
            config_path = os.path.join(configs_dir, config_file)
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    d[config_file] = json.load(f)
        
        return d 