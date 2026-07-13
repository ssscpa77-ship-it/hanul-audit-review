# 소형 VPS 배포 가이드 — 고정 IP·24시간 접속

맥이 꺼져도 교수님이 접속할 수 있도록 **클라우드 서버(VPS)** 에 앱을 올리는 방법입니다.

---

## 1. VPS 업체 추천 (저렴한 순)

| 업체 | 월 비용 | 특징 |
|------|---------|------|
| [Oracle Cloud](https://www.oracle.com/cloud/free/) | **무료** (Always Free) | ARM 4GB, 신용카드 등록. 가입·승인이 까다로울 수 있음 |
| [Hetzner](https://www.hetzner.com/cloud) | **€4.5~** | 독일/핀란드, 가성비 좋음, 카드 결제 |
| [Vultr](https://www.vultr.com) | **$6~** | 도쿄 리전 선택 → 한국에서 빠름 |
| [DigitalOcean](https://www.digitalocean.com) | **$6~** | 설정 쉬움, 싱가포르/도쿄 |
| [Contabo](https://contabo.com) | **€5~** | 스펙 대비 저렴 |
| [네이버 클라우드](https://www.ncloud.com) | **월 1만원~** | 국내, 카드·세금계산서 |

**교수님 접속 속도:** 리전은 **도쿄(Tokyo) / 서울** 권장.

**OS:** Ubuntu 22.04 또는 24.04 LTS

---

## 2. VPS 생성 후 받을 정보

- **공인 IP** (예: `123.45.67.89`) → 이게 **고정 주소**입니다
- **SSH 접속:** `ubuntu@123.45.67.89` (업체마다 `root` 또는 `ubuntu`)

방화벽/보안그룹에서 **22(SSH), 80(HTTP), 443(HTTPS)** 허용.

---

## 3. Mac에서 코드 업로드

```bash
cd /Users/admin/Desktop/ABC05CEO/hanul-002
chmod +x deploy/sync_to_vps.sh
./deploy/sync_to_vps.sh ubuntu@123.45.67.89
```

`.env`(OpenAI 키 등)가 있으면 함께 전송됩니다.  
`kb_store/hanul_kb.sqlite`도 포함되므로 **첫 동기화는 수 분** 걸릴 수 있습니다.

---

## 4. VPS에서 최초 설치 (1회)

```bash
ssh ubuntu@123.45.67.89
sudo bash /opt/hanul-002/deploy/vps_bootstrap.sh /opt/hanul-002
```

완료 후 접속 URL (IP 고정):

| 용도 | URL |
|------|-----|
| 소개 (카톡) | `http://123.45.67.89/?share=1` |
| 앱 | `http://123.45.67.89/?app=1` |

**재부팅해도 IP·URL 동일**합니다. `systemd`가 자동 기동합니다.

---

## 5. HTTPS + 카톡 미리보기 (선택, 권장)

IP만으로는 카톡 링크 미리보기가 잘 안 될 수 있습니다.  
**저렴한 도메인**을 아무 업체에서 사서 **A레코드 → VPS IP**만 연결하면 됩니다.

```bash
# 도메인 예: review.hanul-review.xyz → A레코드 → 123.45.67.89
sudo bash /opt/hanul-002/deploy/vps_bootstrap.sh /opt/hanul-002 review.hanul-review.xyz
```

이후 고정 URL:

- 소개: `https://review.hanul-review.xyz/?share=1`
- 앱: `https://review.hanul-review.xyz/?app=1`

---

## 6. 코드 수정 후 배포

```bash
# Mac
./deploy/sync_to_vps.sh ubuntu@123.45.67.89

# VPS 재시작
ssh ubuntu@123.45.67.89 'sudo systemctl restart hanul-streamlit hanul-gateway'
```

---

## 7. 상태 확인 (VPS)

```bash
systemctl status hanul-streamlit hanul-gateway nginx
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8506/
```

---

## 8. 맥 터널 vs VPS 비교

| | 맥 + Quick Tunnel | 소형 VPS |
|--|-------------------|----------|
| URL | 재시작마다 변경 | **IP/도메인 고정** |
| 24시간 | 맥 켜둬야 함 | **서버가 상시** |
| 월 비용 | 무료 | **$4~6 (약 5천~8천원)** |
| 카톡 공유 | 불안정 | **도메인+HTTPS 시 안정** |

---

## 9. 교수님 카톡 메시지 예시

```
[ABC 5기 신성섭 · 감사조서 Smart Reviewer]

▶ 접속 (고정)
http://123.45.67.89/?share=1

※ PC·Chrome/Safari 권장
```

도메인·HTTPS 적용 후에는 `https://` 주소로 바꿔 전달하세요.
