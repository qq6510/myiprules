import requests
import subprocess
import os

URLS = {
    "amazon_ipv4.mrs": "https://raw.githubusercontent.com/lord-alfred/ipranges/main/amazon/ipv4_merged.txt",
    "microsoft_ipv4.mrs": "https://raw.githubusercontent.com/lord-alfred/ipranges/main/microsoft/ipv4_merged.txt",
    "github_ipv4.mrs": "https://raw.githubusercontent.com/lord-alfred/ipranges/main/github/ipv4_merged.txt"
}

def download_and_convert():
    # 确保输出目录存在
    os.makedirs("output", exist_ok=True)
    
    for output_name, url in URLS.items():
        print(f"正在处理: {output_name}")
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            
            temp_txt = "temp.txt"
            with open(temp_txt, "w") as f:
                f.write(resp.text)
            
            # 使用 ./mihomo 执行转换
            output_path = os.path.join("output", output_name)
            subprocess.run(["./mihomo", "convert-ruleset", "ipcidr", temp_txt, output_path], check=True)
            print(f"转换成功: {output_path}")
            
        except Exception as e:
            print(f"跳过 {output_name}，原因: {e}")
        finally:
            if os.path.exists("temp.txt"):
                os.remove("temp.txt")

if __name__ == "__main__":
    download_and_convert()
