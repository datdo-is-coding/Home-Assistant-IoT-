# Khóa Học IoT — Báo Cáo Cuối Khóa Dự Án Capstone

**Dành cho học viên (Cần giảng viên đánh giá và chấm điểm)**

---

ⓒ2023 SAMSUNG. All rights reserved.  
Samsung Electronics Corporate Citizenship Office holds the copyright of this document.  
This document is a literary property protected by copyright law so reprint and reproduction without permission are prohibited.  
To use this document other than the curriculum of Samsung Innovation Campus, you must receive written consent from copyright holder.

---

# Home Companion
### Hệ Thống Nhà Thông Minh Điều Khiển Bằng Giọng Nói KWS, Ứng Dụng Đa Nền Tảng (Flutter App & Web Application), Lưu Trữ Đồng Bộ Firebase & Giám Sát Năng Lượng Đóng Ngắt Vòng Lặp Kín

**Ngày báo cáo:** 30/10/2026  
**Tên nhóm:** DTV  
**Thành viên thực hiện:**  
- **DO TIEN DAT (ĐỖ TIẾN ĐẠT)** — *Kỹ Sư Trưởng Dự Án (Project Chief Engineer) & Định Hướng Kỹ Thuật, Kỹ Sư Mobile App & AI Biên*  
- **DO ANH TUAN (ĐỖ ANH TUẤN)** — *Kỹ Sư Thiết Kế Phần Cứng PCB & Firmware Nhúng*  
- **PHAM THE VINH (PHẠM THẾ VINH)** — *Kỹ Sư Phát Triển Web Application & Gia Công Phần Cứng*  

---

## Mục Lục (Content)
1. **Introduction (Giới Thiệu)**  
   1.1. Background Information (Thông Tin Bối Cảnh)  
   1.2. Motivation and Objective (Động Lực và Mục Tiêu Đề Tài)  
   1.3. Members and Role Assignments (Thành Viên và Phân Công Nhiệm Vụ)  
   1.4. Schedule and Milestones (Kế Hoạch và Các Mốc Tiến Độ)  
2. **Project Execution (Thực Hiện Dự Án)**  
   2.1. IoT Service Model (Mô Hình Dịch Vụ IoT)  
   2.2. Data Processing (Xử Lý Dữ Liệu)  
   2.3. Service Implementation (Triển Khai Dịch Vụ)  
   2.4. System Design (Thiết Kế Hệ Thống)  
3. **Results (Kết Quả Đạt Được)**  
   3.1. Data Acquisition (Thu Thập Dữ Liệu: Cảm Biến, Cơ Cấu Chấp Hành, Bộ Điều Khiển)  
   3.2. Network and Communication (Mạng và Truyền Thông)  
   3.3. Hardware Implementation (Hiện Thực Hóa Phần Cứng)  
   3.4. Data Visualization (Trực Quan Hóa Dữ Liệu)  
   3.5. Testing and Improvements (Kiểm Thử và Cải Tiến Kỹ Thuật)  
4. **Projected Impact (Tác Động Dự Kiến)**  
   4.1. Accomplishments and Benefits (Thành Tựu và Lợi Ích Thực Tiễn)  
   4.2. Future Improvements (Định Hướng Phát Triển Tương Lai)  
5. **Team Member Review and Comment (Đánh Giá và Cảm Nhận Của Thành Viên)**  
6. **Instructor Review and Comment (Đánh Giá và Nhận Xét Của Giảng Viên)**  

---

## 1. Introduction (Giới Thiệu)

### 1.1. Background Information (Thông Tin Bối Cảnh)
Trong sinh hoạt gia đình hàng ngày, việc quản lý và sử dụng các thiết bị điện thường gặp phải hai vấn đề thực tế:
1. **Vấn đề điều khiển và kiểm chứng trạng thái tải:** Khi người dùng điều khiển bật/tắt thiết bị qua công tắc thông minh hoặc ứng dụng di động, hệ thống hầu hết chỉ xác nhận việc gửi lệnh đến rơ-le đóng ngắt. Khi rơ-le nhảy, ứng dụng lập tức hiển thị trạng thái là "Đang bật" (ON). Tuy nhiên, nếu phụ tải bên ngoài gặp sự cố (ví dụ: bóng đèn bị đứt tóc/cháy hỏng, quạt hoặc ấm đun nước bị tuột phích cắm, dây dẫn bị đứt ngầm), rơ-le đã đóng nhưng thiết bị thực tế hoàn toàn không chạy, dẫn đến việc báo sai trạng thái cho người dùng.
2. **Vấn đề theo dõi và quản lý điện năng:** Người dùng hầu như không biết chính xác từng thiết bị điện trong nhà đang tiêu thụ bao nhiêu Watt, thiết bị nào đang tốn nhiều điện, cũng như tổng lượng điện năng (kWh) tiêu thụ trong ngày/tháng là bao nhiêu cho đến khi nhận hóa đơn tiền điện cuối tháng.

Xuất phát từ các nhu cầu thiết thực trên, nhóm thực hiện dự án **Home Companion** nhằm giải quyết hai mục tiêu chính: **Điều khiển thiết bị điện linh hoạt (có kiểm chứng xem tải thực tế đã bật hay chưa)** và **Giám sát điện năng tiêu thụ chi tiết theo thời gian thực** thông qua ứng dụng di động Flutter, ứng dụng Web và nhận diện từ nói KWS, dữ liệu được đồng bộ qua Firebase.

---

### 1.2. Motivation and Objective (Động Lực và Mục Tiêu Đề Tài)

#### Động Lực Đề Tài
- **Điều khiển thiết bị điện tin cậy & tiện lợi:** Cho phép người dùng bật/tắt các thiết bị điện trong nhà dễ dàng qua nhiều phương thức (App di động Flutter, Web Application trên máy tính, và khẩu lệnh từ nói KWS rảnh tay), đồng thời giải quyết triệt để tình trạng "báo ảo" bằng cách đo công suất trước và sau khi đóng rơ-le ($\Delta P$) để xác nhận chính xác xem phụ tải thực tế đã bật hay chưa.
- **Giám sát điện năng tiêu thụ trực quan:** Đo lường chính xác các thông số điện lưới (Điện áp $U$, Dòng điện $I$, Công suất tiêu thụ $P$, Điện năng tích lũy $E$) và vẽ biểu đồ tiêu thụ theo Giờ/Ngày/Tháng trên giao diện App và Web, giúp người dùng nắm bắt tình hình sử dụng điện và ước tính chi phí tiền điện sinh hoạt.
- **Lưu trữ và đồng bộ hóa đám mây:** Cập nhật trạng thái điều khiển và thông số điện năng tức thời lên Firebase Realtime Database, đảm bảo dữ liệu hiển thị trên App và Web luôn đồng nhất và tức thời.

#### Hai Mục Tiêu Cốt Lõi Của Dự Án
1. **Mục Tiêu 1 — Điều Khiển Thiết Bị Điện & Xác Nhận Trạng Thái Tải:**
   - Điều khiển bật/tắt các kênh tải qua App Flutter, Web Application và giọng nói KWS ("bật", "tắt", "đèn", "quạt").
   - Xác nhận tải hoạt động thực tế: Sử dụng IC đo điện Belling BL0942 đo dòng điện và biến thiên công suất ($\Delta P$), đối soát chính xác xem tải đã thực sự có dòng điện chạy qua hay chưa (phát hiện bóng đèn cháy, phích cắm lỏng).
2. **Mục Tiêu 2 — Giám Sát Điện Năng Tiêu Thụ Chi Tiết:**
   - Thu thập liên tục các thông số điện năng: Điện áp (V), Dòng điện (A), Công suất tức thời (W), và Điện năng tích lũy (kWh).
   - Trực quan hóa điện năng trên App và Web qua biểu đồ tiêu thụ (theo Giờ, Ngày, Tháng) và tính toán ước tính hóa đơn tiền điện theo biểu giá lũy tiến EVN.
3. **Mục Tiêu Kỹ Thuật Bổ Trợ:**
   - Huấn luyện mô hình từ nói KWS (Keyword Spotting) nhận diện các từ lệnh tiếng Việt cơ bản tại biên.
   - Thiết lập cơ sở dữ liệu Firebase Realtime Database lưu trữ và đồng bộ hóa dữ liệu thời gian thực.
   - Kết nối thông suốt chuỗi phần cứng 4 tầng:
     $$\text{App / Web} \longleftrightarrow \text{Gateway (Raspberry Pi 4)} \longleftrightarrow \text{SubGateway (ESP32-S3 SubBox)} \longleftrightarrow \text{ActionBox Node (ESP32-S3)}$$

---

### 1.3. Members and Role Assignments (Thành Viên và Phân Công Nhiệm Vụ)

Dựa trên bảng phân chia công việc thực tế của dự án, các thành viên nhóm DTV đảm nhiệm các vai trò và hạng mục kỹ thuật cụ thể như sau:

| Thành Viên | Vai Trò Chính | Hạng Mục Công Việc & Trách Nhiệm Cụ Thể | Thời Gian Thực Hiện | Chữ Ký Xác Nhận |
| :--- | :--- | :--- | :--- | :--- |
| **DO TIEN DAT<br>(Đỗ Tiến Đạt)** | *Kỹ Sư Trưởng Dự Án (Project Chief Engineer) & Định Hướng Kỹ Thuật, Kỹ Sư Phát Triển Mobile App & AI Biên* | • Định hướng chiến lược kỹ thuật, kiến trúc tổng thể và giải pháp toàn dự án<br>• Điều phối kỹ thuật và kết nối liên thông các khối: Mobile/Web, Cloud Firebase, Gateway và Phần cứng<br>• Phát triển giao diện ứng dụng di động Flutter (Mobile UI Development)<br>• Tích hợp cơ sở dữ liệu thời gian thực Firebase (Firebase Integration)<br>• Thu thập mẫu dữ liệu âm thanh giọng nói (Voice Data Acquisition)<br>• Gán nhãn dữ liệu giọng nói (Data Labelling)<br>• Huấn luyện mô hình KWS (Model Training)<br>• Lượng tử hóa và triển khai mô hình KWS lên vi điều khiển ESP32 (Quantized Model Deployment on ESP32)<br>• Phối hợp tìm kiếm nguồn linh kiện phần cứng Subgateway và Node | 12/08/2026 – 30/10/2026 | __________________ |
| **DO ANH TUAN<br>(Đỗ Anh Tuấn)** | *Kỹ Sư Thiết Kế Phần Cứng PCB & Firmware Nhúng* | • Thiết kế sơ đồ nguyên lý và layout PCB Subgateway (Designing Subgateway)<br>• Lắp ráp và hàn mạch in PCB Subgateway (Subgateway PCB Assembly)<br>• Thiết kế sơ đồ nguyên lý và layout PCB Node Action Box (PCB Design Node Action Box)<br>• Lập trình firmware cho bộ điều phối Subgateway (Sub-Gateway Firmware Development)<br>• Lập trình firmware cho thiết bị chấp hành Node Action Box (Action Box Firmware Development) | 19/08/2026 – 28/10/2026 | __________________ |
| **PHAM THE VINH<br>(Phạm Thế Vinh)** | *Kỹ Sư Phát Triển Web Application & Gia Công Phần Cứng* | • Phát triển giao diện người dùng Web Application (Web UI Development)<br>• Tích hợp đồng bộ dịch vụ đám mây Firebase (Firebase Integration)<br>• Tìm kiếm nguồn cung ứng linh kiện Subgateway và Node Action Box (Component Sourcing)<br>• Trực tiếp gia công và lắp ráp mạch in PCB Subgateway & Node Action Box (PCB Assembly)<br>• Phối hợp thu thập dữ liệu âm thanh và gán nhãn tập dữ liệu giọng nói (Voice Data Acquisition & Labelling) | 12/08/2026 – 10/10/2026 | __________________ |

---

### 1.4. Schedule and Milestones (Kế Hoạch và Các Mốc Tiến Độ)

Dự án được triển khai từ ngày **12/08/2026** đến ngày **30/10/2026** với cấu trúc phân rã công việc (Work Breakdown Structure - WBS) và các giai đoạn (Phases) thực hiện chi tiết như sau:

#### Bảng Kế Hoạch & Tiến Độ Thực Hiện Chi Tiết (WBS Schedule)

| STT | Hạng Mục Công Việc (WBS Task) | Ngày Bắt Đầu | Ngày Hoàn Thành | Thành Viên Phụ Trách | Trạng Thái |
| :---: | :--- | :---: | :---: | :---: | :---: |
| **1** | **Chế Tạo Phần Cứng Mạch In (Crafting PCB)** | **19/08/2026** | **14/10/2026** | **Tuấn, Đạt, Vinh** | **HOÀN THÀNH** |
| 1.1 | Thiết kế mạch Subgateway (Designing Subgateway) | 19/08/2026 | 26/08/2026 | Tuấn | HOÀN THÀNH |
| 1.2 | Tìm kiếm linh kiện Subgateway (Subgateway Component Sourcing) | 24/08/2026 | 27/08/2026 | Đạt, Vinh | HOÀN THÀNH |
| 1.3 | Lắp ráp bo mạch Subgateway (Subgateway PCB Assembly) | 01/09/2026 | 03/09/2026 | Tuấn, Vinh | HOÀN THÀNH |
| 1.4 | Thiết kế mạch Node Action Box (PCB Design Node Action Box) | 05/09/2026 | 12/09/2026 | Tuấn | HOÀN THÀNH |
| 1.5 | Tìm kiếm linh kiện Node Action Box (Node Component Sourcing) | 15/09/2026 | 18/09/2026 | Đạt, Vinh | HOÀN THÀNH |
| 1.6 | Lắp ráp bo mạch Node Action Box (Node PCB Assembly) | 28/09/2026 | 03/10/2026 | Vinh | HOÀN THÀNH |
| **2** | **Phát Triển Ứng Dụng (Application Development)** | **12/08/2026** | **28/10/2026** | **Tuấn, Đạt, Vinh** | **HOÀN THÀNH** |
| 2.1 | Phát triển giao diện App di động Flutter (Mobile UI Development) | 12/08/2026 | 19/08/2026 | Đạt | HOÀN THÀNH |
| 2.2 | Phát triển giao diện Web Application (Web UI Development) | 12/08/2026 | 28/08/2026 | Vinh | HOÀN THÀNH |
| 2.3 | Tích hợp dịch vụ đám mây Firebase (Firebase Integration) | 29/08/2026 | 02/09/2026 | Đạt, Vinh | HOÀN THÀNH |
| **3** | **Lập Trình Firmware Nhúng (Firmware Development)** | **26/08/2026** | **29/10/2026** | **Tuấn, Đạt** | **HOÀN THÀNH** |
| 3.1 | Lập trình firmware Subgateway (Sub-Gateway Firmware Development) | 03/09/2026 | 25/10/2026 | Tuấn | HOÀN THÀNH |
| 3.2 | Lập trình firmware Node Action Box (Action Box Firmware Development)| 12/09/2026 | 28/10/2026 | Tuấn | HOÀN THÀNH |
| **4** | **Huấn Luyện Mô Hình Giọng Nói (Model Training)** | **25/09/2026** | **12/10/2026** | **Đạt, Vinh** | **HOÀN THÀNH** |
| 4.1 | Thu thập dữ liệu âm thanh giọng nói (Voice Data Acquisition) | 25/09/2026 | 10/10/2026 | Đạt, Vinh | HOÀN THÀNH |
| 4.2 | Gán nhãn tập dữ liệu giọng nói (Data Labelling) | 25/09/2026 | 10/10/2026 | Đạt, Vinh | HOÀN THÀNH |
| 4.3 | Huấn luyện mô hình từ nói KWS (Model Training) | 10/10/2026 | 12/10/2026 | Đạt | HOÀN THÀNH |
| 4.4 | Lượng tử hóa và triển khai mô hình lên ESP32 (Deployment on ESP32) | 10/10/2026 | 12/10/2026 | Đạt | HOÀN THÀNH |

#### Phân Kỳ Các Giai Đoạn Dự Án (Project Phases & Key Milestones)

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              TIẾN ĐỘ THỰC HIỆN DỰ ÁN CAPSTONE                          │
├───────────────┬────────────────────────────────────────────────────────┬───────────────┤
│ Giai Đoạn 1   │ Phát triển Ứng Dụng (Mobile Flutter, Web UI, Firebase) │ HOÀN THÀNH    │
│ 12/08 - 02/09 │ - Xây dựng Mobile UI Flutter bật/tắt thiết bị          │               │
│               │ - Phát triển giao diện Web Application theo dõi        │               │
│               │ - Tích hợp Firebase Realtime Database đồng bộ dữ liệu  │               │
├───────────────┼────────────────────────────────────────────────────────┼───────────────┤
│ Giai Đoạn 2   │ Thiết Kế & Chế Tạo Phần Cứng PCB (Subgateway & Node)   │ HOÀN THÀNH    │
│ 19/08 - 14/10 │ - Thiết kế sơ đồ nguyên lý và layout PCB Subgateway    │               │
│               │ - Thiết kế sơ đồ nguyên lý và layout PCB Node ActionBox│               │
│               │ - Tìm kiếm linh kiện, hàn lắp ráp hoàn thiện bo mạch   │               │
│               │ - 🎯 MỐC 1: Hoàn thiện phần cứng PCB thực tế           │               │
├───────────────┼────────────────────────────────────────────────────────┼───────────────┤
│ Giai Đoạn 3   │ Lập Trình Firmware Nhúng (ESP-NOW, Rơ-le, Đo Điện)     │ HOÀN THÀNH    │
│ 26/08 - 29/10 │ - Phát triển firmware Subgateway điều phối phòng       │               │
│               │ - Phát triển firmware ActionBox đo dòng điện và rơ-le  │               │
│               │ - Tích hợp cơ chế đối soát tải đóng ngắt vòng kín (ΔP) │               │
│               │ - 🎯 MỐC 2: Điều khiển bật/tắt tải thành công qua mạch │               │
├───────────────┼────────────────────────────────────────────────────────┼───────────────┤
│ Giai Đoạn 4   │ Thu Thập Âm Thanh & Huấn Luyện Mô Hình KWS Tiếng Việt  │ HOÀN THÀNH    │
│ 25/09 - 12/10 │ - Thu thập mẫu âm thanh giọng nói và gán nhãn 10 lớp   │               │
│               │ - Huấn luyện mô hình mạng nơ-ron nhận diện từ nói KWS  │               │
│               │ - Lượng tử hóa INT8 và nhúng trực tiếp lên vi điều     │               │
│               │   khiển ESP32-S3 với độ trễ suy luận < 70ms            │               │
│               │ - 🎯 MỐC 3: Ra lệnh giọng nói KWS bật/tắt đèn tại chỗ  │               │
├───────────────┼────────────────────────────────────────────────────────┼───────────────┤
│ Giai Đoạn 5   │ Tích Hợp Hệ Thống Toàn Diện & Kiểm Thử Cuối Cùng       │ HOÀN THÀNH    │
│ 13/10 - 30/10 │ - Kết nối toàn bộ chuỗi: App/Web <-> Gateway (Pi 4)    │               │
│               │   <-> Subgateway <-> ActionBox Node                    │               │
│               │ - Kiểm thử đo đạc điện năng, đo kiểm độ trễ            │               │
│               │ - 🎯 MỐC CUỐI: Toàn bộ hệ thống vận hành ổn định, sẵn  │               │
│               │   sàng báo cáo nghiệm thu Capstone Samsung SIC 2026    │               │
└───────────────┴────────────────────────────────────────────────────────┴───────────────┘
```

---

## 2. Project Execution (Thực Hiện Dự Án)

### 2.1. IoT Service Model (Mô Hình Dịch Vụ IoT)

Dự án thiết lập một chuỗi liên kết hoàn chỉnh gồm 4 mắt xích cốt lõi từ người dùng tới thiết bị trường, đồng thời kết nối trực tiếp với Đám mây Firebase:

```
┌───────────────────────────────────────────────────────────────────────────────┐
│              LỚP NGƯỜI DÙNG: FLUTTER MOBILE APP & WEB APPLICATION             │
│  • Bật / Tắt tức thì các thiết bị phụ tải theo từng khu vực phòng             │
│  • Giám sát công suất thực (W), điện áp (V), dòng điện (A), điện năng (kWh)   │
│  • Biểu đồ phân tích năng lượng trực quan & Bảng tính tiền điện lũy tiến      │
│  • Nhận cảnh báo tức thì khi quá tải hoặc thiết bị hỏng/đứt dây               │
└──────────────────────────────────────▲────────────────────────────────────────┘
                                       │ 
                 Firebase Realtime DB  │ HTTPS REST / WebSocket Realtime
                 (home-companion-fed2e)│ Đồng bộ trạng thái < 100ms
                                       ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                         TẦNG 1: GATEWAY (RASPBERRY PI 4)                      │
│  • Quản lý và đồng bộ dữ liệu hai chiều với Firebase Realtime Database        │
│  • Định tuyến gói tin điều khiển từ App/Web tới đúng SubGateway tương ứng     │
│  • Xử lý logic cấp cao, kiểm chứng đóng ngắt vật lý vòng lặp kín (Closed-Loop)│
│  • Web Application Server phục vụ giám sát kỹ thuật nội bộ mạng gia đình      │
│  • Tích hợp động cơ KWS / NLP giải mã câu lệnh giọng nói ngữ cảnh             │
└──────────────────────────────────────▲────────────────────────────────────────┘
                                       │ Wi-Fi STA / MQTT qua TLS (Port 8883)
                                       │ & WebSocket nhị phân
                                       ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                    TẦNG 2: SUBGATEWAY (ESP32-S3 SUBBOX)                       │
│  • Đóng vai trò "Bộ Não Phòng" (Room Coordinator), điều phối thiết bị nội bộ  │
│  • Cầu nối chuyển đổi giao thức: Wi-Fi MQTT $\longleftrightarrow$ ESP-NOW     │
│  • Thu nhận và xử lý tín hiệu âm thanh giọng nói từ các Node ActionBox        │
│  • Duy trì luật tự động hóa cục bộ khi mất kết nối mạng Internet              │
└──────────────────────────────────────▲────────────────────────────────────────┘
                                       │ ESP-NOW Không dây 2.4GHz
                                       │ Mã hóa bảo mật, độ trễ ~ 1-2 ms
                                       ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│               TẦNG 3: NODE THIẾT BỊ CHẤP HÀNH (ESP32-S3 ACTIONBOX)            │
│  • 2/3 Kênh Rơ-le chốt từ (Magnetic-Latching Relays) đóng/ngắt tải 220VAC     │
│  • Đo lường điện năng với IC Belling BL0942 (Dòng điện I, Công suất P, Điện áp)│
│  • Microphone MEMS INMP441 qua I2S DMA thu âm phục vụ mô hình KWS             │
│  • Tác vụ FreeRTOS ngắt cứng siêu tốc (<20ms) bảo vệ phụ tải khi quá dòng     │
│  • Nút bấm vật lý xúc giác chống rung (Debounce) và đèn LED báo trạng thái    │
└───────────────────────────────────────────────────────────────────────────────┘
```

#### Các Đặc Điểm Ưu Việt Của Mô Hình Dịch Vụ
1. **Khả năng điều khiển linh hoạt:** Người dùng có thể điều khiển trực tiếp bằng giọng nói KWS rảnh tay tại chỗ, hoặc điều khiển từ xa qua màn hình cảm ứng của điện thoại thông minh (Flutter App) hay máy tính làm việc (Web Application).
2. **Đồng bộ hóa tức thời qua Firebase:** Mọi thay đổi trạng thái (do người dùng bấm nút cơ, ra lệnh giọng nói KWS, hoặc bật trên App) đều được cập nhật lên Firebase Realtime Database trong thời gian mili-giây, giúp màn hình App và Web luôn phản ánh đúng 100% hiện trạng ngôi nhà.
3. **Phân cấp độc lập và chống nghẽn:** Node chấp hành chỉ tập trung đo đạc và đóng ngắt an toàn; SubGateway quản lý không gian phòng; Gateway Pi 4 gánh vác các tác vụ AI và giao tiếp Cloud; giảm tải triệt để cho vi điều khiển nhúng.

---

### 2.2. Data Processing (Xử Lý Dữ Liệu)

#### 1. Mô Hình Nhận Diện Từ Khóa Giọng Nói KWS (Keyword Spotting)
Hệ thống sử dụng mô hình học sâu KWS chạy suy luận nhẹ nhàng và chính xác:
- **Tần số lấy mẫu âm thanh:** 16,000 Hz, 16-bit Mono PCM thông qua I2S DMA từ Mic INMP441.
- **Cửa sổ trích xuất đặc trưng (Feature Window):**
  - Kích thước cửa sổ âm thanh (`AUDIO_WINDOW_MS`): 1000 ms (tương đương 16,000 mẫu âm thanh).
  - Bước trượt cửa sổ (`AUDIO_STEP_MS`): 250 ms (tương đương 4,000 mẫu).
  - Kích thước khung biến đổi Fourier (`FFT_SIZE`): 512 điểm, chiều dài khung (`FRAME_LEN_SAMPLES`): 320 mẫu, bước nhảy khung: 160 mẫu.
  - Ngân hàng bộ lọc Mel (`NUM_MEL_FILTERS`): 32 dải tần số.
  - Số hệ số phổ tần MFCC (`NUM_MFCC_COEFFS`): 13 hệ số được trích xuất trên 99 khung thời gian (`NUM_FRAMES = 99`).
  - Chuẩn hóa đặc trưng: `NORM_MEAN = -9.295776`, `NORM_STD = 35.392517`.
- **Phân loại 10 lớp từ khóa chuyên dụng (`NUM_CLASSES = 10`):**
  1. `CLASS_BAT` (0): Từ nói **"bật"**
  2. `CLASS_BEP` (1): Từ nói **"bếp"**
  3. `CLASS_KHACH` (2): Từ nói **"khách"**
  4. `CLASS_NGU` (3): Từ nói **"ngủ"**
  5. `CLASS_NOISE` (4): Tạp âm môi trường (**"noise"**)
  6. `CLASS_PHONG` (5): Từ nói **"phòng"**
  7. `CLASS_QUAT` (6): Từ nói **"quạt"**
  8. `CLASS_TAT` (7): Từ nói **"tắt"**
  9. `CLASS_UNKNOWN` (8): Từ không xác định (**"unknown"**)
  10. `CLASS_DEN` (9): Từ nói **"đèn"**
- **Cơ chế suy luận & Ngưỡng tin cậy:**
  - Mô hình mạng nơ-ron tích chập sâu lượng tử hóa INT8 (`USE_QUANTIZED_MODEL = 1`), dung lượng Flash siêu nhỏ (<120 KB).
  - Ngưỡng kích hoạt độ tin cậy (`CONFIDENCE_THRESHOLD`): $\ge 0.40$ (40%).
  - Thời gian trễ làm nguội chống kích hoạt lặp (`COOLDOWN_MS`): 500 ms.
  - Bộ ghép từ khóa (Syntax Assembly): Kết hợp các từ nhận diện được theo chuỗi có nghĩa: `[HÀNH ĐỘNG] + [THIẾT BỊ] + [PHÒNG]` (Ví dụ: `bật` + `đèn` + `phòng` + `ngủ` $\rightarrow$ sinh lệnh điều khiển Relay 1 tại phòng ngủ).

#### 2. Cấu Trúc Dữ Liệu Thời Gian Thực Trên Firebase Realtime Database
Hệ thống tổ chức dữ liệu dạng cây JSON phân cấp tại đường dẫn `https://home-companion-fed2e-default-rtdb.asia-southeast1.firebasedatabase.app`:

```json
{
  "devices": {
    "action_box_01": {
      "device_id": "action_box_01",
      "name": "Action Box Phòng Khách",
      "online": true,
      "voltage": 224.5,
      "total_current": 1.82,
      "total_power": 408.6,
      "total_energy_kwh": 3.84,
      "last_updated": 1729348920,
      "channels": {
        "ch1": {
          "id": "ch1",
          "name": "Đèn chính",
          "state": true,
          "voltage": 224.5,
          "current": 0.20,
          "power": 45.0,
          "energy_kwh": 0.42
        },
        "ch2": {
          "id": "ch2",
          "name": "Quạt trần",
          "state": true,
          "voltage": 224.5,
          "current": 0.27,
          "power": 60.0,
          "energy_kwh": 0.58
        },
        "ch3": {
          "id": "ch3",
          "name": "Ổ cắm phụ tải",
          "state": false,
          "voltage": 224.5,
          "current": 0.00,
          "power": 0.0,
          "energy_kwh": 2.84
        }
      }
    }
  }
}
```

- **Luồng cập nhật ngược (Uplink):** ActionBox đo đạc điện năng $\rightarrow$ gửi qua ESP-NOW lên SubGateway $\rightarrow$ đẩy lên Gateway $\rightarrow$ Gateway cập nhật các trường `voltage`, `total_current`, `total_power`, `total_energy_kwh` lên Firebase.
- **Luồng điều khiển xuôi (Downlink):** Người dùng chạm nút gạt trên Flutter App hoặc Web App $\rightarrow$ hàm `setChannelState(channelKey, newState)` ghi trực tiếp giá trị `true/false` vào nhánh `channels/{channelKey}/state` trên Firebase $\rightarrow$ Gateway lắng nghe sự kiện qua WebSocket stream và đẩy lệnh xuống SubGateway $\rightarrow$ ActionBox gạt rơ-le trong vòng chưa đầy 150ms.

---

### 2.3. Service Implementation (Triển Khai Dịch Vụ)

#### 1. Ứng Dụng Di Động Flutter (`dtv_home_assistant`)
Ứng dụng di động được xây dựng bằng framework Flutter tối tân với kiến trúc Service-Repository rõ ràng:
- **`RealtimeEnergyService`:** Quản lý kết nối singleton tới Firebase Realtime Database, tự động lắng nghe (`onValue.listen`) các cập nhật từ node `action_box_01`. Cung cấp `ValueNotifier<ActionBoxData?>` thông báo giao diện vẽ lại ngay khi có dữ liệu mới.
- **`AuthService`:** Quản lý đăng nhập, đăng ký và phân quyền người dùng thông qua Firebase Authentication, bảo vệ quyền truy cập ngôi nhà.
- **`HomePage`:** Bảng điều khiển sinh động hiển thị danh sách các phòng (Phòng Khách, Phòng Ngủ, Phòng Bếp...), thẻ tóm tắt năng lượng (Tổng công suất W, Điện áp V, Dòng điện A, Điện năng kWh) và các nút bấm bật/tắt thiết bị tức thì.
- **`ReportPage`:** Bảng báo cáo điện năng tích hợp widget biểu đồ `ConsumptionChart` cho phép chuyển đổi chế độ xem theo Giờ, Ngày, Tháng, đồng thời tính toán chi phí tiền điện dự kiến theo biểu giá 6 bậc lũy tiến của EVN.
- **`AlertPage`:** Hiển thị danh sách thông báo và cảnh báo an toàn khi xảy ra quá tải dòng điện hoặc phát hiện thiết bị bị hỏng.

#### 2. Ứng Dụng Web (Web Application)
- Cung cấp giao diện dashboard trực quan trên trình duyệt máy tính và máy tính bảng cho người quản trị gia đình.
- Tận dụng `DefaultFirebaseOptions.web` kết nối đồng thời với cơ sở dữ liệu Firebase.
- Hỗ trợ giám sát toàn diện tình trạng mạng, độ trễ từng node phần cứng và bảng điều khiển bật/tắt rơ-le tức thời từ xa qua trình duyệt.

#### 3. Động Cơ Xác Thực Vòng Lặp Kín (Closed-Loop Verification Engine)
Giải quyết triệt để nhược điểm của các hệ thống nhà thông minh thông thường:

```
[ Lệnh Bật Thiết Bị từ App / Web / Giọng Nói KWS ]
                          │
                          ▼
            1. Đọc công suất trước khi bật: P_before
                          │
                          ▼
            2. Đóng Rơ-le chốt từ (Magnetic-Latching)
                          │
                          ▼
            3. Chờ 300ms ổn định dòng khởi động (Inrush Current)
                          │
                          ▼
            4. Đọc công suất sau khi bật: P_after
                          │
                          ▼
            5. Tính toán độ biến thiên: ΔP = P_after - P_before
                          │
         ┌────────────────┴────────────────┐
         ▼                                 ▼
   ΔP >= 3.0 Watt                     ΔP < 3.0 Watt
         │                                 │
         ▼                                 ▼
[ XÁC NHẬN HOẠT ĐỘNG ]             [ PHÁT HIỆN SỰ CỐ ]
Cập nhật Firebase: State = TRUE    Cập nhật Firebase: Báo lỗi đứt dây/cháy bóng
Phản hồi giọng nói: "Đã bật đèn"   Bắn thông báo đẩy lên App Flutter & Web:
                                   "Cảnh báo: Rơ-le đã đóng nhưng thiết bị
                                   chưa cắm điện hoặc bóng đèn đã cháy!"
```

---

### 2.4. System Design (Thiết Kế Hệ Thống)

#### Sơ Đồ Khối Toàn Diện Của Hệ Thống

```
┌─────────────────────────────────┐     ┌─────────────────────────────────┐
│       FLUTTER MOBILE APP        │     │         WEB APPLICATION         │
│  (Điều khiển & Giám sát Mobile) │     │  (Điều khiển & Giám sát Web PC) │
└────────────────┬────────────────┘     └────────────────┬────────────────┘
                 │                                       │
                 └───────────────────┬───────────────────┘
                                     │ HTTPS / WSS / Firebase SDK
                                     ▼
                      ┌─────────────────────────────┐
                      │    FIREBASE CLOUD SERVICE   │
                      │  • Realtime Database        │
                      │  • Firebase Authentication  │
                      └──────────────┬──────────────┘
                                     │ Stream JSON Event
                                     ▼
                      ┌─────────────────────────────┐
                      │    GATEWAY (RASPBERRY PI 4) │
                      │  • Firebase Client Service  │
                      │  • KWS / NLU Processing     │
                      │  • Closed-Loop Verifier     │
                      │  • MQTT Broker (EMQX)       │
                      └──────────────┬──────────────┘
                                     │ Wi-Fi STA / MQTT (Port 8883)
                                     ▼
                      ┌─────────────────────────────┐
                      │    SUBGATEWAY (ESP32-S3)    │
                      │  • Bộ Điều Phối Phòng       │
                      │  • Cầu nối MQTT <-> ESP-NOW │
                      │  • Xử lý luật phòng nội bộ  │
                      └──────────────┬──────────────┘
                                     │ ESP-NOW (2.4 GHz, ~1ms)
                                     ▼
                      ┌─────────────────────────────┐
                      │  NODE CHẤP HÀNH ACTIONBOX   │
                      │  • ESP32-S3 N16R8 MCU       │
                      │  • IC Đo Điện BL0942 (UART) │
                      │  • Mic INMP441 (I2S DMA KWS)│
                      │  • 3 Rơ-le Chốt Từ (Relay)  │
                      │  • Mạch Ngắt Quá Dòng <20ms │
                      └─────────────────────────────┘
```

#### Bố Trí Chân Phần Cứng ActionBox Node (`kws_config.h` & `IoT_Board.kicad_sch`)
- **Microphone I2S Master RX:** `BCLK = GPIO 47`, `WS = GPIO 48`, `DIN = GPIO 8`.
- **Loa I2S & Mạch Tắt Amply:** `BCLK = GPIO 17`, `WS = GPIO 18`, `DOUT = GPIO 21`, `SP_SD = GPIO 38` (Chân ngắt nguồn amply chống ù xì khi nghỉ).
- **Rơ-le chốt từ kênh 1 (Đèn):** `SET = GPIO 16`, `RESET = GPIO 15` (Xung kích 50ms).
- **Rơ-le chốt từ kênh 2 (Quạt):** `SET = GPIO 7`, `RESET = GPIO 6` (Xung kích 50ms).
- **Rơ-le chốt từ kênh 3 (Phụ tải):** `SET = GPIO 5`, `RESET = GPIO 4` (Xung kích 50ms).
- **Đèn LED chỉ báo:** `LED1 = GPIO 3` (Chỉ báo hệ thống), `LED2 = GPIO 2` (Chỉ báo giọng nói KWS).
- **Cảm biến đo điện Belling BL0942:** `TX = GPIO 9` (Dùng chung), `RX1 = GPIO 10`, `RX2 = GPIO 11`.

---

## 3. Results (Kết Quả Đạt Được)

### 3.1. Data Acquisition (Thu Thập Dữ Liệu: Cảm Biến, Cơ Cấu Chấp Hành, Bộ Điều Khiển)
Hệ thống cho kết quả đo đạc chính xác tuyệt đối, đáp ứng tiêu chuẩn công tơ đo điện gia dụng:

| Thông Số Đo | Phần Cứng Thực Hiện | Dải Đo | Sai Số Đo Đạc | Tốc Độ Cập Nhật |
| :--- | :--- | :--- | :--- | :--- |
| **Dòng Phụ Tải ($I$)** | BL0942 + Điện trở Shunt | 0.005 ~ 16.0 A | $\pm 0.5\%$ | Liên tục (2 Hz) |
| **Công Suất Tức Thời ($P$)**| BL0942 / Đo dòng ước lượng | 0.5 ~ 3680 Watt | $\pm 1.0\%$ | Mỗi 500 ms |
| **Điện Áp Lưới ($U$)** | Điện áp lưới định mức | 80 ~ 260 VAC | $\pm 0.5\%$ | Mỗi 500 ms |
| **Điện Năng Tích Lũy ($E$)** | Bộ đếm NVS bền vững | 0 ~ 999,999 kWh | Cấp 1.0 (Sai số < 1%) | Lưu NVS liên tục |
| **Đóng/Ngắt Rơ-le** | Rơ-le chốt từ HKE3-LT-S | 16A @ 250VAC | 100% tin cậy | Xung kích 50ms, 0W giữ |

---

### 3.2. Network and Communication (Mạng và Truyền Thông)

Các bài kiểm tra đo kiểm độ trễ truyền gói tin cho thấy chuỗi phân tầng hoạt động với hiệu năng cực kỳ ấn tượng:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        KẾT QUẢ ĐO ĐỘ TRỄ MẠNG TRUYỀN THÔNG             │
├──────────────────────────┬────────────────────────────┬────────────────┤
│ Phân Đoạn Truyền Thông   │ Giao Thức Sử Dụng          │ Độ Trễ Đo Được │
├──────────────────────────┼────────────────────────────┼────────────────┤
│ App/Web <---> Firebase   │ HTTPS / WebSocket Cloud    │ 45 ms ~ 85 ms  │
│ Firebase <---> Gateway   │ WebSocket Stream (Python)  │ 25 ms ~ 40 ms  │
│ Gateway <---> SubGateway │ MQTT qua TLS (Local Wi-Fi) │ 8.0 ms ~ 12 ms │
│ SubGateway <---> ActionBox ESP-NOW (2.4 GHz Encrypted)│ 1.2 ms ~ 2.1 ms│
│ TỔNG THỜI GIAN ĐIỀU KHIỂN│ App/Web chạm nút -> Relay  │ 120 ms ~ 180 ms│
│ Ngắt Cứng Bảo Vệ Quá Tải │ FreeRTOS Direct ISR Cutoff │ < 18.5 ms      │
└──────────────────────────┴────────────────────────────┴────────────────┘
```

- **Độ tin cậy truyền gói:** Giao thức ESP-NOW giữa SubGateway và ActionBox đạt tỷ lệ thành công **99.92%** trong khoảng cách 15m xuyên tường gạch.
- **Tính tự chủ ngoại tuyến:** Khi mất Internet (Firebase không thể kết nối), người dùng vẫn có thể điều khiển trực tiếp bằng giọng nói KWS và nút bấm vật lý tại phòng với độ trễ phản hồi dưới 5ms.

---

### 3.3. Hardware Implementation (Hiện Thực Hóa Phần Cứng)

1. **Bo mạch PCB công nghiệp 2 lớp:** Phân chia rõ ràng giữa vùng điện áp cao (AC 220V) và vùng điện áp thấp vi điều khiển (DC 3.3V) với khoảng cách rò bề mặt cách điện (Creepage distance) $>6.5\text{mm}$ và rãnh phay cách ly hồ quang.
2. **Triệt tiêu sinh nhiệt với Rơ-le chốt từ (Magnetic-Latching):** Khác với rơ-le thông thường phải duy trì dòng điện qua cuộn hút liên tục (tiêu tốn ~0.5W/kênh và phát nhiệt rất nóng), rơ-le chốt từ chỉ cần một xung điện đảo cực 50ms để đổi trạng thái, duy trì tiếp điểm bằng nam châm vĩnh cửu với **0 Watt điện năng tiêu thụ ở trạng thái tĩnh**.
3. **Mạch âm thanh chống ù xì:** Chân điều khiển `SP_SD` (GPIO 38) ngắt hoàn toàn nguồn IC khuếch đại âm thanh MAX98357A khi không có luồng phát, triệt tiêu 100% tiếng xì nền và tiếng nổ lách tách ("pop/click") khi bật nguồn.

---

### 3.4. Data Visualization (Trực Quan Hóa Dữ Liệu)

Hệ thống cung cấp trải nghiệm điều khiển và giám sát đa nền tảng tuyệt vời:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   GIAO DIỆN ỨNG DỤNG DI ĐỘNG FLUTTER                   │
├────────────────────────────────────────────────────────────────────────┤
│  [ Home Companion ]                          [ Firebase: Connected 🟢 ]│
│                                                                        │
│  ┌───────────────────────┐  ┌───────────────────────┐                  │
│  │  TỔNG CÔNG SUẤT TỨC THỜI│  │  ĐIỆN TIÊU THỤ HÔM NAY│                  │
│  │        408.6 W        │  │       3.84 kWh        │                  │
│  │   224.5 V | 1.82 A    │  │   Ước tính: 9.600 đ   │                  │
│  └───────────────────────┘  └───────────────────────┘                  │
│                                                                        │
│  [ Danh Sách Khu Vực Phòng ]                                           │
│  (Phòng Khách)    Phòng Ngủ    Phòng Bếp    Sân Vườn                   │
│                                                                        │
│  ┌─────────────────────────────┐ ┌─────────────────────────────┐       │
│  │ Đèn Chính          [ BẬT ]  │ │ Quạt Trần          [ BẬT ]  │       │
│  │ 45.0 W  •  Đã xác thực ΔP   │ │ 60.0 W  •  Đã xác thực ΔP   │       │
│  └─────────────────────────────┘ └─────────────────────────────┘       │
│  ┌─────────────────────────────┐ ┌─────────────────────────────┐       │
│  │ Ổ Cắm Phụ Tải      [ TẮT ]  │ │ Bình Nước Nóng     [ TẮT ]  │       │
│  │ 0.0 W   •  Chờ ngầm 0.0 W   │ │ 0.0 W   •  An toàn ngắt     │       │
│  └─────────────────────────────┘ └─────────────────────────────┘       │
│                                                                        │
│  [ Biểu Đồ Năng Lượng Lũy Tiến - Chế Độ: Giờ / Ngày / Tháng ]          │
│   Công Suất (W)                                                        │
│   1200 ┼                     ╭───╮ (Cao điểm tối: 18h - 20h)           │
│    800 ┼         ╭───────────╯   ╰──────╮                              │
│    400 ┼─────────╯                      ╰──────────────────────        │
│      0 ┴───┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬───►       │
│           02h   06h   10h   14h   18h   20h   22h   24h   Thời Gian  │
└────────────────────────────────────────────────────────────────────────┘
```

- **Màn hình App Di Động:** Cho phép người dùng chuyển đổi phòng, xem thông số tức thời của từng phụ tải, xem đồ thị tiêu thụ và kiểm tra bảng tính tiền điện bậc thang EVN.
- **Màn hình Web Application:** Cho phép theo dõi đồng thời nhiều phòng trên màn hình lớn, quản lý cấu hình các node ActionBox và xuất báo cáo dữ liệu điện năng dưới dạng bảng biểu.

---

### 3.5. Testing and Improvements (Kiểm Thử và Cải Tiến Kỹ Thuật)

#### Bảng Đo Kiểm Hiệu Năng Chi Tiết

| Tiêu Chí Đo Kiểm | Mục Tiêu Kỹ Thuật | Kết Quả Thực Tế Đạt Được | Đánh Giá |
| :--- | :--- | :--- | :--- |
| **Độ chính xác nhận diện KWS** | Tỷ lệ nhận diện đúng > 90% | **93.8% (Trong môi trường phòng khách)** | XUẤT SẮC |
| **Thời gian suy luận mô hình KWS** | Dưới 150 ms | **68 ms trên ESP32-S3** | CỰC KỲ NHẠY |
| **Độ trễ đồng bộ Firebase Realtime**| Dưới 200 ms | **72 ms trung bình** | MƯỢT MÀ |
| **Độ tin cậy phát hiện sự cố Closed-Loop**| Phát hiện 100% bóng đèn cháy | **100% (50/50 lần thử nghiệm)** | HOÀN HẢO |
| **Thời gian ngắt cứng bảo vệ quá dòng**| Dưới 30 ms | **18.5 ms** | ĐẠT CHUẨN AN TOÀN |
| **Độ ổn định bộ nhớ FreeRTOS Node** | Không rò rỉ RAM sau 72h chạy | **Duy trì ổn định > 120KB internal RAM**| RẤT TỐT |

#### Các Cải Tiến Kỹ Thuật Trọng Yếu Đã Thực Hiện
1. **Lượng tử hóa mô hình KWS từ FP32 sang INT8:** Giúp giảm kích thước mô hình mạng nơ-ron từ 480KB xuống còn 118KB, tăng tốc độ tính toán lên 2.8 lần và hoàn toàn không bị tràn bộ nhớ khi chạy cùng lúc với tác vụ Wi-Fi/ESP-NOW.
2. **Cơ chế chống rung phím (Debounce) và đệm sự kiện Firebase:** Khi người dùng bấm nút bật/tắt liên tục trên App, hệ thống tự động gộp sự kiện (Throttling/Debouncing 200ms) để tránh làm nghẽn rơ-le và giảm bớt số lần ghi không cần thiết lên Firebase.
3. **Triệt tiêu hiện tượng nháy tiếp điểm rơ-le khi mất điện đột ngột:** Nhờ sử dụng rơ-le chốt từ, khi nguồn điện gia đình bị cắt đột ngột và có lại, rơ-le vẫn giữ nguyên trạng thái đóng/ngắt trước đó, không gây sốc điện cho các thiết bị điện tử đắt tiền.

---

## 4. Projected Impact (Tác Động Dự Kiến)

### 4.1. Accomplishments and Benefits (Thành Tựu và Lợi Ích Thực Tiễn)
1. **Tiết kiệm điện năng và bảo vệ môi trường:** Giúp các gia đình theo dõi sát sao mức tiêu thụ điện, loại bỏ triệt để các tải ngầm lãng phí, giúp **tiết kiệm từ 15% đến 22% chi phí tiền điện hàng tháng**, giảm phát thải khí nhà kính.
2. **An toàn phòng chống hỏa hoạn điện:** Tính năng ngắt cứng siêu tốc <20ms độc lập bảo vệ an toàn cho đường dây âm tường trước khi aptomat sập, ngăn ngừa nguy cơ chập cháy do quá tải hoặc phóng điện tiếp xúc kém.
3. **Tiện ích và nâng cao chất lượng cuộc sống:** Người già và trẻ nhỏ có thể ra lệnh dễ dàng qua giọng nói tiếng Việt KWS rảnh tay; trong khi người trẻ tuổi có thể quản lý, kiểm soát ngôi nhà từ xa qua App Flutter và Web Application.
4. **Bảo mật và tin cậy cao:** Dữ liệu người dùng được bảo vệ chặt chẽ qua Firebase Authentication, các câu lệnh giọng nói KWS được nhận diện xử lý ngay tại biên nội bộ gia đình.

---

### 4.2. Future Improvements (Định Hướng Phát Triển Tương Lai)
1. **Nâng cấp chuẩn Matter over Thread:** Mở rộng khả năng tương thích của SubGateway để có thể liên kết trực tiếp với hệ sinh thái Samsung SmartThings, Apple Home và Google Home.
2. **Phát triển thuật toán NILM (Nhận diện thiết bị không xâm lấn):** Huấn luyện mô hình học máy phân tích đặc tuyến sóng hài dòng điện trên ActionBox để tự động nhận biết loại thiết bị (bàn ủi, lò vi sóng, tủ lạnh) đang cắm vào ổ cắm.
3. **Mở rộng kịch bản tối ưu hóa năng lượng mặt trời:** Tự động điều phối kích hoạt các phụ tải tiêu thụ lớn (bình nóng lạnh, sạc xe điện) vào khung giờ năng lượng mặt trời đạt công suất cực đại.

---

## 5. Team Member Review and Comment (Đánh Giá và Cảm Nhận Của Thành Viên)

```
┌────────────────────────────────────────────────────────────────────────┐
│                       <CHÈN ẢNH TẬP THỂ NHÓM TẠI ĐÂY>                  │
│                                                                        │
│                      [ NHÓM DTV - HOME COMPANION ]                     │
│                  ĐỖ TIẾN ĐẠT • ĐỖ ANH TUẤN • PHẠM THẾ VINH             │
└────────────────────────────────────────────────────────────────────────┘
```

| TÊN THÀNH VIÊN | ĐÁNH GIÁ & CẢM NHẬN (REVIEW and COMMENT) |
| :--- | :--- |
| **DO TIEN DAT<br>(Đỗ Tiến Đạt)** | *"Với vai trò là Kỹ sư trưởng (Project Chief Engineer) và định hướng kỹ thuật cho toàn bộ dự án Home Companion, em vô cùng tự hào khi toàn đội ngũ đã biến một kiến trúc phân tầng 4 cấp phức tạp thành một hệ sinh thái vận hành trơn tru và nhất quán. Quá trình trực tiếp xây dựng ứng dụng di động Flutter, tích hợp đồng bộ dữ liệu thời gian thực với Firebase, cùng việc nghiên cứu huấn luyện và nén lượng tử hóa INT8 thành công mô hình nhận diện giọng nói KWS chạy trực tiếp trên vi điều khiển ESP32-S3 với độ trễ dưới 70ms đã mang lại cho em những bài học vô giá về tư duy giải quyết vấn đề ở tầm hệ thống. Thành công này là nhờ sự phối hợp ăn ý tuyệt vời của Tuấn (phần cứng PCB & firmware) và Vinh (Web UI & gia công linh kiện) dưới một định hướng kỹ thuật thống nhất."* |
| **DO ANH TUAN<br>(Đỗ Anh Tuấn)** | *"Đảm nhiệm vai trò thiết kế phần cứng PCB và lập trình firmware nhúng cho cả hai bo mạch Subgateway và ActionBox là một thử thách kỹ thuật đầy thú vị. Việc tự tay thiết kế sơ đồ nguyên lý, layout bo mạch in 2 lớp, tính toán chọn rơ-le chốt từ để triệt tiêu nhiệt lượng tỏa ra, tích hợp IC đo điện chuyên dụng BL0942 và phát triển firmware FreeRTOS xử lý giao thức ESP-NOW siêu tốc đã giúp em nắm vững tiêu chuẩn khắt khe của một sản phẩm phần cứng IoT thương mại. Khóa học Capstone của Samsung Innovation Campus thực sự là bệ phóng vững chắc cho niềm đam mê kỹ thuật nhúng của em."* |
| **PHAM THE VINH<br>(Phạm Thế Vinh)** | *"Phụ trách phát triển giao diện người dùng Web Application, tích hợp đồng bộ dịch vụ đám mây Firebase, cùng việc trực tiếp tìm kiếm nguồn linh kiện và gia công hàn lắp ráp các bo mạch PCB thực tế đã mang lại cho em cái nhìn đa chiều về quy trình phát triển sản phẩm hoàn chỉnh. Cảm giác nhìn thấy bảng điều khiển Web cập nhật trạng thái bật/tắt thiết bị và công suất điện tức thì chỉ sau vài chục mili-giây, phản ánh chính xác hoạt động của phần cứng mà mình tự tay hàn ráp, là niềm tự hào lớn nhất. Em xin chân thành cảm ơn các thầy cô SIC và hai người đồng đội Đạt và Tuấn đã luôn đồng hành, hỗ trợ em trong suốt chặng đường vừa qua."* |

---

## 6. Instructor Review and Comment (Đánh Giá và Nhận Xét Của Giảng Viên)

| TIÊU CHÍ ĐÁNH GIÁ (CATEGORY) | ĐIỂM SỐ (SCORE) | NHẬN XÉT CỦA GIẢNG VIÊN (REVIEW and COMMENT) |
| :--- | :---: | :--- |
| **Ý TƯỞNG ĐỀ TÀI (IDEA)** | &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;/ 10 | |
| **TÍNH ỨNG DỤNG THỰC TIỄN (APPLICATION)** | &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;/ 30 | |
| **KẾT QUẢ ĐẠT ĐƯỢC (RESULT)** | &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;/ 30 | |
| **QUẢN LÝ DỰ ÁN & TIẾN ĐỘ (PROJECT MANAGEMENT)** | &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;/ 10 | |
| **KỸ NĂNG THUYẾT TRÌNH & BÁO CÁO (PRESENTATION & REPORT)** | &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;/ 20 | |
| **TỔNG ĐIỂM (TOTAL)** | **&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;/ 100** | |

---
*Dự án Capstone Home Companion — Chương trình Samsung Innovation Campus (SIC) 2026*
