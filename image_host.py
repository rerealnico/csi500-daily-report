"""
图床上传模块 - 将图表上传到免费图床，获取公开URL用于微信推送

支持多个图床，自动重试，失败不影响主流程
"""
import requests
from pathlib import Path


def _try_smms_v1(filepath: str) -> str | None:
    """尝试 sm.ms v1 API（无需注册）"""
    try:
        with open(filepath, "rb") as f:
            resp = requests.post(
                "https://sm.ms/api/upload",
                files={"smfile": f},
                timeout=15,
            )
        data = resp.json()
        if data.get("code") == "success":
            return data["data"]["url"]
        elif data.get("code") == "image_repeated" and data.get("images"):
            return data["images"]
    except Exception:
        pass
    return None


def _try_smms_v2(filepath: str) -> str | None:
    """尝试 sm.ms v2 API"""
    try:
        with open(filepath, "rb") as f:
            resp = requests.post(
                "https://sm.ms/api/v2/upload",
                files={"smfile": f},
                timeout=15,
            )
        data = resp.json()
        if data.get("code") == "success":
            return data["data"]["url"]
        elif data.get("code") == "image_repeated" and data.get("images"):
            return data["images"]
    except Exception:
        pass
    return None


def _try_imgurl(filepath: str) -> str | None:
    """尝试 imgurl.org 图床（国内可访问）"""
    try:
        with open(filepath, "rb") as f:
            resp = requests.post(
                "https://imgurl.org/upload",
                files={"file": f},
                timeout=15,
            )
        data = resp.json()
        if data.get("status") == 200:
            return data["data"]["url"]
    except Exception:
        pass
    return None


UPLOAD_PROVIDERS = [_try_smms_v2, _try_smms_v1, _try_imgurl]


def upload_to_hosting(filepath: str) -> str | None:
    """
    上传图片到图床，自动重试多个服务

    Parameters
    ----------
    filepath : str
        图片文件路径

    Returns
    -------
    str or None
        图片公开URL，全部失败返回 None
    """
    for upload_fn in UPLOAD_PROVIDERS:
        url = upload_fn(filepath)
        if url:
            print(f"  [图床] ✅ 上传成功: {url[:60]}...")
            return url
    print(f"  [图床] ⚠️ 所有图床均失败，跳过图片上传")
    return None


def upload_images(filepaths: list[str]) -> list[str]:
    """
    批量上传图片

    Parameters
    ----------
    filepaths : list[str]
        图片文件路径列表

    Returns
    -------
    list[str]
        成功上传的图片URL列表
    """
    urls = []
    for fp in filepaths:
        if Path(fp).exists():
            print(f"  [图床] 上传 {Path(fp).name}...")
            url = upload_to_hosting(fp)
            if url:
                urls.append(url)
    return urls
