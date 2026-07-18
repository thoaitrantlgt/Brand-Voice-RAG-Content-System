# Ke hoach Profile, Blog Generation va Evaluation Pipeline

## 1. Muc tieu

Xay dung pipeline co the:

1. Nhap du lieu tu Google Sheet.
2. Tao nhieu Brand Voice Profile theo tung project hoac nguoi dung.
3. Sinh thu blog tu cac chu de trong sheet.
4. Danh gia blog sinh ra bang so lieu cu the.
5. Tach hoan toan tai lieu kien thuc va blog mau de tranh he thong lay nham van phong lam su that.

## 2. Thiet ke du lieu theo Project

Moi nguoi dung hoac thuong hieu co mot `project_id`. Mot project co the co nhieu profile, vi du:

- Profile "Thanh nhac chuyen mon".
- Profile "Marketing khoa hoc".
- Profile "Giong ca nhan cua giang vien".

Trong moi project chia thanh ba cluster logic:

| Cluster | Noi dung | Duoc dung khi nao |
|---|---|---|
| `knowledge` | Tai lieu cung cap thong tin, kien thuc, san pham | Tra cuu du kien khi viet |
| `brand_voice` | Blog mau duoc danh gia tot | Hoc giong van, cau truc, cach dien dat |
| `evaluation` | Bai giu lai de kiem thu | Chi danh gia, khong dua vao RAG luc viet |

Moi chunk trong Chroma phai co metadata:

```text
project_id
profile_id
document_id
cluster
source_url
category
human_rating
dataset_split
```

Khi sinh blog:

- RAG noi dung chi query `knowledge`.
- Vi du van phong chi query `brand_voice` cung `profile_id`.
- Khong bao gio query `evaluation`.

## 3. Luu metadata ben vung trong SQLite

Thay phan metadata tai lieu dang nam trong RAM bang cac bang:

- `projects`
- `documents`
- `brand_voice_profiles`
- `evaluation_runs`
- `evaluation_items`

`documents` luu nguon, cluster, rating, category, trang thai parse va so chunk. Chroma tiep tuc giu vector; SQLite giu quan he va lich su.

Viec nay xu ly van de hien tai: danh sach tai lieu co the mat sau khi restart backend.

## 4. Chia du lieu 70/30

Sheet hien co 50 bai, gom 5 category, moi category 10 bai.

Chia stratified theo ca:

- Category.
- Nhom rating thap `1-3`.
- Nhom rating tot `4-5`.

Ket qua muc tieu:

- Train: khoang 35 bai.
- Test: khoang 15 bai.
- Moi category: 7 train va 3 test.
- Dung seed co dinh de lan chay sau cho cung ket qua.

Profile chi hoc tu cac bai train co rating `4-5`. Bai rating `1-3` khong duoc xem la mau phong cach tot; chung dung lam negative examples de xac dinh dac diem can tranh va hieu chinh bo cham diem.

Vi toan bo sheet chi co 15 bai rating `4-5`, tap profile thuc te se co khoang 10-11 bai. Bao cao phai canh bao day la tap kha nho.

## 5. Tao Brand Voice Profile

Profile duoc tong hop tu cac bai tot trong train set, gom:

- Tone va muc do chuyen mon.
- Cach mo bai, chuyen doan, ket bai.
- Do dai cau va doan.
- Cach dung heading va danh sach.
- Tu/cum tu thuong dung.
- Tu/cum tu can tranh.
- CTA.
- Dau hieu rieng theo tung category.

Profile phai luu:

- Phien ban.
- Danh sach tai lieu nguon.
- Ngay tao.
- So bai dung de train.
- Cac thong ke dinh luong.
- `project_id` va `profile_id`.
- Trang thai active/inactive.

Khong ghi de profile cu; moi lan train tao mot version de so sanh.

## 6. Sinh blog thu tu chu de trong Sheet

Lay chu de tu 15 bai test, uu tien chay truoc 10 bai, moi category 2 bai.

Voi moi chu de:

1. Planner tao dan y.
2. RAG lay thong tin tu cluster `knowledge`.
3. Writer nhan Brand Voice Profile.
4. Co the lay toi da 2-3 doan mau gan nhat tu `brand_voice`.
5. Editor kiem tra style va cac tu cam.
6. Ban sinh thu duoc luu vao `evaluation_items`, khong dua thang vao bang blog production.

Nhu vay co the so sanh:

- Bai goc trong test set.
- Bai he thong sinh theo cung chu de.
- Ket qua theo tung category.

## 7. Bo danh gia

Moi bai sinh ra co cac chi so:

| Chi so | Trong so du kien |
|---|---:|
| Tone va voice | 25% |
| Cau truc bai | 20% |
| Writing fingerprint | 20% |
| Tu vung va terminology | 15% |
| Kha nang doc | 10% |
| Tuan thu CTA/quy tac | 10% |

Dieu kien pass ban dau:

- Tong diem tu `80/100`.
- Khong co forbidden term nghiem trong.
- Structure tu `75`.
- Writing fingerprint tu `60`.
- Khong su dung tai lieu ngoai project.
- Co du nguon kien thuc cho cac khang dinh quan trong.

Ngoai automated score, moi bai ho tro human review `1-5`. Sau do do:

- Pearson va Spearman correlation.
- MAE giua diem may va diem nguoi.
- Pass rate.
- Diem trung binh theo category.
- False positive: may cham tot nhung nguoi cham thap.
- False negative: may cham thap nhung nguoi danh gia tot.

Muc tieu vong dau:

- Correlation toi thieu `0.5`.
- MAE quy doi khong qua `20/100`.
- It nhat `70%` blog sinh thu dat dieu kien pass.

Hien pipeline chi dat Pearson khoang `0.18`, Spearman `0.14`, MAE khoang `35.22`; vi vay chua nen coi score hien tai la tieu chuan chat luong cuoi cung.

## 8. API va script

Giu API hien tai nhung bo sung `project_id`, `profile_id`, `cluster`.

Cac luong moi:

```text
POST /projects
POST /documents/import-sheet
POST /brand-voice/profiles/train
POST /evaluation/runs
GET  /evaluation/runs/{run_id}
POST /evaluation/items/{item_id}/review
```

Dong thoi co CLI de chay benchmark khong can frontend:

```powershell
python scripts/evaluate_tss_pipeline.py `
  --project tss `
  --split 0.7 `
  --generated-count 10 `
  --seed 42
```

## 9. Thu tu trien khai

1. Them schema SQLite va repository cho project, document, profile, evaluation.
2. Chuyen metadata tai lieu tu RAM sang SQLite.
3. Them filter `project_id + cluster + profile_id` cho Chroma retrieval.
4. Refactor script hien tai thanh pipeline import, split, train, generate va eval.
5. Tao profile version dau tien tu train set.
6. Sinh 10 blog thu tu chu de trong test set.
7. Xuat bao cao JSON, CSV va Markdown.
8. Them API de chay lai benchmark va nhap human review.
9. Viet unit va integration tests.
10. Chay focused tests, sau do full backend test suite.

## 10. Tieu chi hoan thanh

- Import du 50 bai hop le.
- Split khoang 35 train va 15 test, can bang category.
- Profile khong su dung bai test.
- Bai rating thap khong duoc dung lam mau van phong tot.
- Retrieval khong tron `knowledge`, `brand_voice` va `evaluation`.
- Hai project khac nhau khong truy xuat duoc du lieu cua nhau.
- Restart backend khong lam mat metadata.
- Sinh duoc 10 blog thu va bao cao diem theo tung bai/category.
- Co the gan human rating de hieu chinh bo cham diem o lan chay tiep theo.
