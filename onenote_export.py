#!/usr/bin/env python3
"""
OneNote 전체 내용을 로컬 Markdown으로 동기화
Azure 앱으로 한번만 인증 후 전체 다운로드
"""

import os
import json
import requests
from pathlib import Path
from html2text import html2text
from msal import PublicClientApplication

# 설정
CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"  # MS Graph Explorer
SCOPES = ["Notes.Read"]
OUTPUT_DIR = Path("./OneNote_Backup")

class OneNoteExporter:
    def __init__(self):
        self.token = None
        self.headers = None
        
    def authenticate(self):
        """Device Code Flow 인증"""
        app = PublicClientApplication(CLIENT_ID, authority="https://login.microsoftonline.com/common")
        
        flow = app.initiate_device_flow(scopes=SCOPES)
        print(f"\n{'='*50}")
        print(flow['message'])
        print(f"{'='*50}\n")
        
        result = app.acquire_token_by_device_flow(flow)
        
        if "access_token" in result:
            self.token = result['access_token']
            self.headers = {'Authorization': f'Bearer {self.token}'}
            print("✅ 인증 성공!\n")
            return True
        else:
            print(f"❌ 인증 실패: {result.get('error_description')}")
            return False
    
    def get_notebooks(self):
        """모든 노트북 가져오기"""
        url = "https://graph.microsoft.com/v1.0/me/onenote/notebooks"
        response = requests.get(url, headers=self.headers)
        return response.json().get('value', [])
    
    def get_sections(self, notebook_id):
        """노트북의 모든 섹션 가져오기"""
        url = f"https://graph.microsoft.com/v1.0/me/onenote/notebooks/{notebook_id}/sections"
        response = requests.get(url, headers=self.headers)
        return response.json().get('value', [])
    
    def get_pages(self, section_id):
        """섹션의 모든 페이지 가져오기"""
        url = f"https://graph.microsoft.com/v1.0/me/onenote/sections/{section_id}/pages"
        response = requests.get(url, headers=self.headers)
        return response.json().get('value', [])
    
    def get_page_content(self, page_id):
        """페이지 HTML 내용 가져오기"""
        url = f"https://graph.microsoft.com/v1.0/me/onenote/pages/{page_id}/content"
        response = requests.get(url, headers=self.headers)
        return response.text if response.ok else ""
    
    def html_to_markdown(self, html):
        """HTML을 Markdown으로 변환"""
        try:
            return html2text(html)
        except:
            return html
    
    def sanitize_filename(self, name):
        """파일명 안전하게 변환"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '_')
        return name[:200]  # 길이 제한
    
    def export_all(self):
        """전체 OneNote 내용 동기화"""
        OUTPUT_DIR.mkdir(exist_ok=True)
        
        notebooks = self.get_notebooks()
        print(f"📚 노트북 {len(notebooks)}개 발견\n")
        
        for nb in notebooks:
            nb_name = self.sanitize_filename(nb['displayName'])
            nb_path = OUTPUT_DIR / nb_name
            nb_path.mkdir(exist_ok=True)
            
            print(f"📖 {nb['displayName']}")
            
            sections = self.get_sections(nb['id'])
            for section in sections:
                sec_name = self.sanitize_filename(section['displayName'])
                sec_path = nb_path / sec_name
                sec_path.mkdir(exist_ok=True)
                
                print(f"  📁 {section['displayName']}")
                
                pages = self.get_pages(section['id'])
                for page in pages:
                    page_name = self.sanitize_filename(page['title'])
                    page_file = sec_path / f"{page_name}.md"
                    
                    # HTML 내용 가져와서 Markdown 변환
                    html_content = self.get_page_content(page['id'])
                    markdown = self.html_to_markdown(html_content)
                    
                    # 메타데이터 추가
                    metadata = f"""---
title: {page['title']}
created: {page['createdDateTime']}
modified: {page['lastModifiedDateTime']}
page_id: {page['id']}
---

"""
                    
                    # 파일 저장
                    with open(page_file, 'w', encoding='utf-8') as f:
                        f.write(metadata + markdown)
                    
                    print(f"    ✓ {page['title']}")
        
        print(f"\n✅ 완료! 저장 위치: {OUTPUT_DIR.absolute()}")
        
        # 인덱스 파일 생성
        self.create_index()
    
    def create_index(self):
        """전체 인덱스 파일 생성"""
        index_file = OUTPUT_DIR / "INDEX.md"
        
        with open(index_file, 'w', encoding='utf-8') as f:
            f.write("# OneNote Backup Index\n\n")
            
            for nb_dir in sorted(OUTPUT_DIR.iterdir()):
                if not nb_dir.is_dir():
                    continue
                    
                f.write(f"## {nb_dir.name}\n\n")
                
                for sec_dir in sorted(nb_dir.iterdir()):
                    if not sec_dir.is_dir():
                        continue
                        
                    f.write(f"### {sec_dir.name}\n\n")
                    
                    for page_file in sorted(sec_dir.glob("*.md")):
                        rel_path = page_file.relative_to(OUTPUT_DIR)
                        f.write(f"- [{page_file.stem}]({rel_path})\n")
                    
                    f.write("\n")


def main():
    print("🚀 OneNote 전체 동기화 시작\n")
    
    exporter = OneNoteExporter()
    
    # 인증
    if not exporter.authenticate():
        return
    
    # 전체 동기화
    exporter.export_all()


if __name__ == "__main__":
    main()