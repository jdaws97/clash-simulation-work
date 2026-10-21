import re,sys,html
t=open(sys.argv[1],encoding='utf-8',errors='replace').read()
for blk in t.split('class="vc_column baseItem"')[1:]:
    g=lambda p: (re.search(p,blk,re.S) or [None,None])[1]
    bid=g(r'#(\d+)\s*</div>'); b=g(r'data-builder="([^"]*)"'); tags=re.findall(r'<li>\s*<span class="special">([^<]*)</span>\s*<span>([^<]*)</span>',blk)
    img=g(r'href="(https://clashchamps.com/cdn-cgi/imagedelivery/[^"]+/image1920)"'); up=g(r'Uploaded:\s*([0-9-]+)'); dl=g(r'(\d+) downloads'); link=g(r'OpenLayout&amp;id=([^"]+)"')
    print(bid,b,tags,up,dl,img,link,sep=' | ')
