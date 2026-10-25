import base64, os, re
from urllib.parse import urlparse
import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
import main as core
router=APIRouter(prefix='/api',tags=['integrations'])
TIMEOUT=httpx.Timeout(45.0,connect=10.0)
def env(name):
 value=os.getenv(name,'').strip()
 if not value:raise HTTPException(status_code=503,detail=f'Integration is not configured: add {name} in Render → Environment.')
 return value
def repo_parts(value):
 p=urlparse(value.strip())
 if p.scheme!='https' or p.netloc.lower() not in ('github.com','www.github.com'):raise HTTPException(status_code=422,detail='Use a GitHub URL such as https://github.com/owner/repo.')
 parts=[x for x in p.path.strip('/').split('/') if x]
 if len(parts)<2 or not all(re.fullmatch(r'[A-Za-z0-9_.-]+',x) for x in parts[:2]):raise HTTPException(status_code=422,detail='Invalid repository URL.')
 return parts[0],parts[1].removesuffix('.git')
class Place(BaseModel):place:str=Field(min_length=1,max_length=160)
class ImagePrompt(BaseModel):prompt:str=Field(min_length=3,max_length=1800)
class CodePrompt(BaseModel):prompt:str=Field(min_length=3,max_length=8000);filename:str=Field(default='generated.txt',min_length=1,max_length=100)
class Repo(BaseModel):url:str=Field(min_length=10,max_length=300)
class Proposal(BaseModel):owner:str;repo:str;path:str=Field(min_length=1,max_length=240);content:str=Field(max_length=100000);message:str=Field(min_length=5,max_length=200);branch:str=Field(default='main',min_length=1,max_length=100)
@router.get('/integrations')
async def integrations(request:Request):
 await core.current_user(request)
 return {'groq':bool(os.getenv('GROQ_API_KEY')),'cloudflare':bool(os.getenv('CLOUDFLARE_ACCOUNT_ID') and os.getenv('CLOUDFLARE_API_TOKEN')),'cesium':bool(os.getenv('CESIUM_ION_TOKEN')),'openweather':bool(os.getenv('OPENWEATHER_API_KEY')),'github':bool(os.getenv('GITHUB_TOKEN'))}
@router.get('/config/public')
async def public_config(request:Request):
 await core.current_user(request);return {'cesium_token':os.getenv('CESIUM_ION_TOKEN',''),'weather_tiles':bool(os.getenv('OPENWEATHER_API_KEY'))}

@router.get('/weather/tiles/{layer}/{z}/{x}/{y}')
async def weather_tile(layer:str,z:int,x:int,y:int,request:Request):
 await core.current_user(request)
 allowed={'clouds_new','precipitation_new','pressure_new','wind_new','temp_new'}
 if layer not in allowed or z<0 or z>18 or x<0 or y<0 or x>=2**z or y>=2**z: raise HTTPException(status_code=404,detail='Weather tile not found.')
 key=env('OPENWEATHER_API_KEY')
 async with httpx.AsyncClient(timeout=TIMEOUT) as c: r=await c.get(f'https://tile.openweathermap.org/map/{layer}/{z}/{x}/{y}.png',params={'appid':key})
 if r.status_code!=200: raise HTTPException(status_code=502,detail='OpenWeather tile unavailable. Check API plan and key permissions.')
 from fastapi.responses import Response
 return Response(content=r.content,media_type='image/png',headers={'Cache-Control':'public, max-age=300'})

@router.post('/weather')
async def weather(body:Place,request:Request):
 await core.current_user(request);key=env('OPENWEATHER_API_KEY')
 async with httpx.AsyncClient(timeout=TIMEOUT) as c:
  geo=await c.get('https://api.openweathermap.org/geo/1.0/direct',params={'q':body.place,'limit':1,'appid':key})
  if geo.status_code!=200:raise HTTPException(status_code=502,detail='OpenWeather geocoding failed. Check API key and account access.')
  places=geo.json()
  if not places:raise HTTPException(status_code=404,detail='Place not found. Try a city name.')
  p=places[0];cur=await c.get('https://api.openweathermap.org/data/2.5/weather',params={'lat':p['lat'],'lon':p['lon'],'units':'metric','appid':key});fc=await c.get('https://api.openweathermap.org/data/2.5/forecast',params={'lat':p['lat'],'lon':p['lon'],'units':'metric','appid':key})
 if cur.status_code!=200:raise HTTPException(status_code=502,detail='OpenWeather current weather request failed.')
 w=cur.json();f=fc.json() if fc.status_code==200 else {}
 return {'place':p.get('name'),'country':p.get('country'),'lat':p['lat'],'lon':p['lon'],'temperature':w['main']['temp'],'feels_like':w['main']['feels_like'],'humidity':w['main']['humidity'],'pressure':w['main']['pressure'],'wind_speed':w.get('wind',{}).get('speed',0),'wind_deg':w.get('wind',{}).get('deg',0),'description':w.get('weather',[{}])[0].get('description',''),'icon':w.get('weather',[{}])[0].get('icon','01d'),'clouds':w.get('clouds',{}).get('all',0),'forecast':[{'time':x['dt_txt'],'temp':x['main']['temp'],'description':x['weather'][0]['description'],'icon':x['weather'][0]['icon'],'rain':x.get('rain',{}).get('3h',0),'snow':x.get('snow',{}).get('3h',0)} for x in f.get('list',[])[:8]],'source':'OpenWeather'}
@router.post('/image')
async def image(body:ImagePrompt,request:Request):
 await core.current_user(request);account=env('CLOUDFLARE_ACCOUNT_ID');token=env('CLOUDFLARE_API_TOKEN');model=os.getenv('CLOUDFLARE_IMAGE_MODEL','@cf/black-forest-labs/flux-1-schnell')
 async with httpx.AsyncClient(timeout=TIMEOUT) as c:r=await c.post(f'https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}',headers={'Authorization':f'Bearer {token}'},json={'prompt':body.prompt})
 if r.status_code>=400:raise HTTPException(status_code=502,detail=f'Cloudflare image generation failed ({r.status_code}). Check model access and token permissions.')
 mime=r.headers.get('content-type','')
 if mime.startswith('image/'):raw=r.content;mime=mime.split(';')[0]
 else:
  try:
   result=r.json().get('result',{});encoded=result.get('image') or result.get('data')
   if isinstance(encoded,list):encoded=encoded[0]
   raw=base64.b64decode(encoded);mime='image/png'
  except Exception:raise HTTPException(status_code=502,detail='Unexpected Cloudflare image response.')
 return {'mime':mime,'image_base64':base64.b64encode(raw).decode(),'filename':'aether-image.png'}
@router.post('/code')
async def code(body:CodePrompt,request:Request):
 user=await core.current_user(request)
 if not os.getenv('GROQ_API_KEY'):raise HTTPException(status_code=503,detail='Set GROQ_API_KEY to generate code files.')
 prompt='Generate the complete requested file. Return only file contents, without Markdown fences or explanations. Request: '+body.prompt
 result=await core.generate_reply(prompt,user);result=re.sub(r'^\s*```[A-Za-z0-9_-]*\s*\n','',result);result=re.sub(r'\n```\s*$','',result)
 name=re.sub(r'[^A-Za-z0-9_.-]','_',body.filename)[:100] or 'generated.txt'
 return {'filename':name,'content':result,'bytes':len(result.encode())}
@router.post('/github/analyze')
async def github_analyze(body:Repo,request:Request):
 await core.current_user(request);owner,repo=repo_parts(body.url);headers={'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'};token=os.getenv('GITHUB_TOKEN','').strip()
 if token:headers['Authorization']=f'Bearer {token}'
 async with httpx.AsyncClient(timeout=TIMEOUT,follow_redirects=True) as c:
  r=await c.get(f'https://api.github.com/repos/{owner}/{repo}',headers=headers)
  if r.status_code==404:raise HTTPException(status_code=404,detail='Repository not found or not accessible. Private repositories require GITHUB_TOKEN.')
  if r.status_code>=400:raise HTTPException(status_code=502,detail=f'GitHub API error ({r.status_code}).')
  meta=r.json();branch=meta.get('default_branch','main');tr=await c.get(f'https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}',params={'recursive':'1'},headers=headers);tree=tr.json().get('tree',[]) if tr.status_code==200 else []
  rd=await c.get(f'https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md')
 files=[{'path':x['path'],'size':x.get('size',0),'type':x.get('type')} for x in tree if x.get('type')=='blob'][:150]
 return {'name':meta.get('full_name'),'description':meta.get('description'),'private':meta.get('private'),'default_branch':branch,'language':meta.get('language'),'stars':meta.get('stargazers_count'),'url':meta.get('html_url'),'files':files,'readme':rd.text[:10000] if rd.status_code==200 else '', 'note':'Structural overview from repository metadata and README; not a full security audit.'}
def validate_path(body):
 if not re.fullmatch(r'[A-Za-z0-9_.-]+',body.owner) or not re.fullmatch(r'[A-Za-z0-9_.-]+',body.repo):raise HTTPException(status_code=422,detail='Invalid owner/repository.')
 if body.path.startswith('/') or '..' in body.path.split('/') or '\\' in body.path:raise HTTPException(status_code=422,detail='Unsafe file path.')
 if body.branch.startswith('-') or not re.fullmatch(r'[A-Za-z0-9_./-]+',body.branch):raise HTTPException(status_code=422,detail='Invalid branch name.')
@router.post('/github/propose')
async def propose(body:Proposal,request:Request):
 await core.current_user(request);validate_path(body)
 return {'ok':True,'owner':body.owner,'repo':body.repo,'path':body.path,'branch':body.branch,'message':body.message,'content':body.content,'requires_confirmation':True,'note':'Preview only. No GitHub changes have been made.'}
@router.post('/github/apply')
async def apply(body:Proposal,request:Request):
 await core.current_user(request);validate_path(body);token=env('GITHUB_TOKEN');headers={'Authorization':f'Bearer {token}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'};url=f'https://api.github.com/repos/{body.owner}/{body.repo}/contents/{body.path}'
 async with httpx.AsyncClient(timeout=TIMEOUT) as c:
  cur=await c.get(url,headers=headers,params={'ref':body.branch});payload={'message':body.message,'content':base64.b64encode(body.content.encode()).decode(),'branch':body.branch}
  if cur.status_code==200:payload['sha']=cur.json().get('sha')
  elif cur.status_code!=404:raise HTTPException(status_code=502,detail=f'Could not read file ({cur.status_code}). Check token permissions.')
  result=await c.put(url,headers=headers,json=payload)
 if result.status_code not in (200,201):raise HTTPException(status_code=502,detail=f'GitHub rejected write ({result.status_code}); token needs Contents: write access.')
 data=result.json();return {'ok':True,'commit':data.get('commit',{}).get('html_url'),'path':body.path,'message':'Commit created. Review it in GitHub.'}
