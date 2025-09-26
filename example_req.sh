addr=''
g_id_token=''
curl -X POST "http://localhost:8000/validate" \
     -H "Authorization: Bearer $g_id_token" \
     -H "Content-Type: application/json" \
     -d "{\"image_url\": \"$addr\"}"
