from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

import google.genai
import google.auth.transport.requests
import google.oauth2.id_token

import sqlite3, os, requests, tempfile, json, base64

app = FastAPI()

genai_client = google.genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='token')
request_adapter = google.auth.transport.requests.Request()

prompt = """
	Determine if the image shows a person drinking a Heineken beer.
	Return in structured JSON a list of your reasoning steps
	and a yes/no conclusion.
	"""

class ImageRequest(BaseModel):
	image_url: str

DB_PATH = 'history.db'
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()
cur.execute("""
	CREATE TABLE IF NOT EXISTS history (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	user_email TEXT,
	image TEXT,
	gemini TEXT,
	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP )
	""")
conn.commit()

def get_current_user (
	token: str = Depends(oauth2_scheme)
):
	try:
		id_info = google.oauth2.id_token.verify_oauth2_token(token, request_adapter)
		return id_info['email']
	except Exception as e:
		raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


@app.post('/validate')
async def validate (
	body: ImageRequest,
	user_email: str = Depends(get_current_user)
):
	url = body.image_url
	r = requests.get(url)
	if r.status_code != 200:
		raise HTTPException(status_code=400, detail='Failed to download image')

	tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
	tmp.write(r.content)
	tmp.close()

	img = genai_client.files.upload(
		file=tmp.name,
		config={ 'mime_type': r.headers['Content-Type'] }
	)

	resp = genai_client.models.generate_content(
		model='gemini-2.5-flash',
		contents=[ prompt, img ]
	)

	cleaned = resp.text.strip().removeprefix('```json').removesuffix('```').strip()
	parsed = json.loads(cleaned)
	imgb64 = base64.b64encode(r.content)
	os.remove(tmp.name)

	cur.execute("""
		INSERT INTO history
		(user_email, image, gemini)
		VALUES (?, ?, ?)
		""", ( user_email, url, cleaned ) )
	conn.commit()

	return {
		'image': imgb64,
		'gemini': parsed
	}

@app.get('/history')
async def history (
	user_email: str = Depends(get_current_user)
):
	cur.execute("""
		SELECT id, image, gemini, created_at
		FROM requests WHERE user_email=?
		ORDER BY created_at DESC
		""", ( user_email, ) )
	rows = cur.fetchall()
	return [{
		'id': r[0],
		'image': r[1],
		'gemini': json.loads(r[2]),
		'created_at': r[3]
	} for r in rows ]

