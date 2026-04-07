import requests

# 네이버 API 키 설정
client_id = "1utkxzcyf0"  # 네이버 클라우드 플랫폼에서 발급받은 클라이언트 ID
client_secret = "CLq8enG0sVdhCI5ppsJvSZR8JTW4ORVBvLUtBpnw"  # 네이버 클라우드 플랫폼에서 발급받은 클라이언트 시크릿

# 고정 문자열 주소
address = '분당구 불정로 6'

# 네이버 Geocoding API 호출 함수 정의
def geocode_address(address):
    # url = f"https://naveropenapi.apigw.ntruss.com/map-geocode/v2/geocode?query={address}"
    url = f"https://maps.apigw.ntruss.com/map-geocode/v2/geocode?query={address}"
    headers = {
        'X-NCP-APIGW-API-KEY-ID': client_id,
        'X-NCP-APIGW-API-KEY': client_secret
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if data['addresses']:
            location = data['addresses'][0]
            return location['y'], location['x']
        else:
            return None, None
    else:
        print(f"Error {response.status_code}: {response.text}")
        return None, None

# 주소를 좌표로 변환
latitude, longitude = geocode_address(address)

# 결과 출력
if latitude and longitude:
    print(f"주소: {address}")
    print(f"위도: {latitude}")
    print(f"경도: {longitude}")
else:
    print("좌표를 찾을 수 없습니다.")