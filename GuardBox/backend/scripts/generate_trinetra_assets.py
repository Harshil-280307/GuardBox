import base64
import os

def main():
    logo_path = r'E:\GuardBox\frontend\public\trinetra-logo-transparent.png'
    emblem_path = r'E:\GuardBox\frontend\public\trinetra-emblem.png'

    with open(logo_path, 'rb') as f:
        logo_b64 = base64.b64encode(f.read()).decode('utf-8')

    with open(emblem_path, 'rb') as f:
        emblem_b64 = base64.b64encode(f.read()).decode('utf-8')

    svg_logo = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 682" width="100%" height="100%">
  <image href="data:image/png;base64,{logo_b64}" x="0" y="0" width="1024" height="682" />
</svg>'''

    with open(r'E:\GuardBox\frontend\public\trinetra-logo.svg', 'w', encoding='utf-8') as f:
        f.write(svg_logo)
    with open(r'E:\GuardBox\frontend\src\assets\trinetra-logo.svg', 'w', encoding='utf-8') as f:
        f.write(svg_logo)

    svg_favicon = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="100%" height="100%">
  <defs>
    <radialGradient id="bgGrad" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#0F2E1E" stop-opacity="0.6" />
      <stop offset="100%" stop-color="#07111C" stop-opacity="0" />
    </radialGradient>
  </defs>
  <circle cx="256" cy="256" r="240" fill="url(#bgGrad)" />
  <image href="data:image/png;base64,{emblem_b64}" x="36" y="80" width="440" height="352" />
</svg>'''

    with open(r'E:\GuardBox\frontend\public\favicon.svg', 'w', encoding='utf-8') as f:
        f.write(svg_favicon)
    with open(r'E:\GuardBox\frontend\src\assets\trinetra-emblem.svg', 'w', encoding='utf-8') as f:
        f.write(svg_favicon)

    print("Official TRINETRA SVG & Web assets successfully created!")

if __name__ == '__main__':
    main()
