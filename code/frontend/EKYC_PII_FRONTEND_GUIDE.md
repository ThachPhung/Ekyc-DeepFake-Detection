# Huong dan Frontend: hien thi du lieu eKYC goc cho Admin/Reviewer

## Muc tieu

Backend hien dang mask thong tin nhay cam cho user thuong, vi du:

```json
{
  "parsed_fields": {
    "id_number": "********3456",
    "full_name": "N***** V** A"
  }
}
```

Sau thay doi moi, backend se luu them ban goc da ma hoa bang public key. Chi API danh cho `admin` hoac `ekyc_reviewer` moi co the tra ve du lieu goc, neu backend duoc cau hinh private key.

Frontend **khong can xu ly public/private key**.

## Role duoc xem du lieu goc

User duoc xem du lieu goc khi:

```ts
user.is_superuser === true || user.role === "ekyc_reviewer"
```

Day la logic frontend dang dung cho trang `/admin/ekyc`.

## API can dung

### Danh sach eKYC cho admin/reviewer

```http
GET /api/v1/ekyc/requests/
```

Endpoint nay da yeu cau token cua admin/reviewer.

### Chi tiet eKYC cho admin/reviewer

```http
GET /api/v1/ekyc/requests/{request_id}/admin-detail
```

Nen dung endpoint nay khi mo modal/detail cua mot request.

## Field quan trong

Frontend doc field:

```ts
response.ocr_result
```

Voi user thuong, `ocr_result` van la masked data.

Voi admin/reviewer, `ocr_result` se la:

- Du lieu goc neu backend co private key va decrypt thanh cong.
- Du lieu masked neu backend chua cau hinh private key hoac decrypt that bai.

Vi vay frontend nen hien thi binh thuong theo `ocr_result`, khong can goi endpoint rieng de decrypt.

## Vi du render

```tsx
const fields = request.ocr_result?.parsed_fields ?? request.ocr_result ?? {};

return (
  <dl>
    <dt>So giay to</dt>
    <dd>{fields.id_number || fields.passport_number || "-"}</dd>

    <dt>Ho ten</dt>
    <dd>{fields.full_name || "-"}</dd>

    <dt>Ngay sinh</dt>
    <dd>{fields.date_of_birth || "-"}</dd>

    <dt>Dia chi</dt>
    <dd>{fields.place_of_residence || fields.address || "-"}</dd>
  </dl>
);
```

## Luu y bao mat

- Khong luu `ocr_result` vao `localStorage` hoac `sessionStorage`.
- Khong log `ocr_result` ra console trong production.
- Khong gui `ocr_result` sang analytics/Sentry/client log.
- Neu co nut copy/download, chi hien cho admin/reviewer.
- Private key chi nam o backend. Frontend khong duoc nhan key.

## Cach test nhanh

1. Dang nhap bang user thuong.
2. Goi `/api/v1/ekyc/requests/{request_id}`.
3. Kiem tra thong tin nhay cam bi mask.
4. Dang nhap bang admin hoac staff reviewer.
5. Goi `/api/v1/ekyc/requests/{request_id}/admin-detail`.
6. Kiem tra `ocr_result.parsed_fields.id_number` hien so goc neu backend co private key.

## Neu van thay masked data o trang admin

Co 3 kha nang:

- Request cu duoc tao truoc khi co tinh nang encrypt original data.
- Backend chua cau hinh `EKYC_PII_PRIVATE_KEY_PEM` hoac `EKYC_PII_PRIVATE_KEY_PATH`.
- Worker chua cau hinh `EKYC_PII_PUBLIC_KEY_PEM` hoac `EKYC_PII_PUBLIC_KEY_PATH`, nen request moi khong co ban goc de decrypt.
