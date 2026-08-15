import os

from fairseq import checkpoint_utils


def get_index_path_from_model(sid):
    """Get index path from model filename"""
    # For standalone version, we'll return empty string if no index_root is set
    index_root = os.environ.get("index_root", "")
    if not index_root or not os.path.exists(index_root):
        return ""
        
    return next(
        (
            f
            for f in [
                os.path.join(root, name)
                for root, _, files in os.walk(index_root, topdown=False)
                for name in files
                if name.endswith(".index") and "trained" not in name
            ]
            if sid.split(".")[0] in f
        ),
        "",
    )


def load_hubert(config):
    """Load Hubert model for feature extraction"""
    # Try to find hubert model in assets directory
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    hubert_path = os.path.join(current_dir, "assets", "hubert", "hubert_base.pt")
    
    if not os.path.exists(hubert_path):
        # Fallback to environment variable or default path
        hubert_path = os.environ.get("hubert_path", "assets/hubert/hubert_base.pt")
        
    if not os.path.exists(hubert_path):
        raise FileNotFoundError(
            f"Hubert model not found at {hubert_path}. "
            "Please download hubert_base.pt and place it in assets/hubert/"
        )
    
    models, _, _ = checkpoint_utils.load_model_ensemble_and_task(
        [hubert_path],
        suffix="",
    )
    hubert_model = models[0]
    hubert_model = hubert_model.to(config.device)
    if config.is_half:
        hubert_model = hubert_model.half()
    else:
        hubert_model = hubert_model.float()
    return hubert_model.eval()
