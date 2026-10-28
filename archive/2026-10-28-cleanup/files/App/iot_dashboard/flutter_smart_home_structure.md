# 🏠 Cấu Trúc Dự Án Flutter — Smart Home IoT Monitoring (Frontend)

> Tài liệu mô tả cấu trúc thư mục và giải thích chức năng từng phần, dùng làm tham chiếu khi xây dựng UI theo phong cách dashboard (Clean Architecture + BLoC).

---

## 📁 Cấu Trúc Tổng Quan

```
lib/
├── main.dart
│
├── core/
│   ├── constants/
│   │   ├── app_colors.dart
│   │   ├── app_typography.dart
│   │   ├── app_constants.dart
│   │   ├── app_dimens.dart
│   │   └── enums.dart
│   ├── theme/
│   │   ├── app_theme.dart
│   │   ├── light_theme.dart
│   │   └── dark_theme.dart
│   ├── utils/
│   │   ├── responsive_helper.dart
│   │   ├── size_config.dart
│   │   ├── electricity_calculator.dart
│   │   └── formatters.dart
│   └── extensions/
│       ├── string_extension.dart
│       ├── num_extension.dart
│       └── date_extension.dart
│
├── data/
│   ├── models/
│   │   ├── room_model.dart
│   │   ├── device_model.dart
│   │   ├── energy_record_model.dart
│   │   ├── alert_model.dart
│   │   ├── user_profile_model.dart
│   │   ├── dashboard_summary_model.dart
│   │   └── chart_data_model.dart
│   ├── mock_data/
│   │   ├── mock_rooms.dart
│   │   ├── mock_devices.dart
│   │   ├── mock_energy_records.dart
│   │   └── mock_alerts.dart
│   └── repositories/
│       ├── room_repository.dart
│       ├── device_repository.dart
│       ├── energy_repository.dart
│       ├── alert_repository.dart
│       └── dashboard_repository.dart
│
├── logic/
│   ├── dashboard/
│   │   ├── dashboard_bloc.dart
│   │   ├── dashboard_event.dart
│   │   └── dashboard_state.dart
│   ├── energy_monitor/
│   │   ├── energy_bloc.dart
│   │   ├── energy_event.dart
│   │   └── energy_state.dart
│   ├── report/
│   │   ├── report_bloc.dart
│   │   ├── report_event.dart
│   │   └── report_state.dart
│   ├── device_control/
│   │   ├── device_bloc.dart
│   │   ├── device_event.dart
│   │   └── device_state.dart
│   ├── alert/
│   │   ├── alert_bloc.dart
│   │   ├── alert_event.dart
│   │   └── alert_state.dart
│   ├── navigation/
│   │   ├── navigation_bloc.dart
│   │   ├── navigation_event.dart
│   │   └── navigation_state.dart
│   └── settings/
│       ├── settings_bloc.dart
│       ├── settings_event.dart
│       └── settings_state.dart
│
├── routes/
│   ├── app_routes.dart
│   └── route_generator.dart
│
├── pages/
│   ├── home/
│   │   ├── home_page.dart
│   │   ├── home_layout.dart
│   │   ├── dashboard_provider.dart
│   │   └── room_detail_page.dart
│   ├── report/
│   │   ├── report_page.dart
│   │   ├── report_tab_view.dart
│   │   └── invoice_export_view.dart
│   ├── alerts/
│   │   ├── alerts_page.dart
│   │   ├── alert_timeline.dart
│   │   └── alert_detail_page.dart
│   ├── settings/
│   │   ├── settings_page.dart
│   │   ├── tariff_settings_page.dart
│   │   ├── alert_threshold_page.dart
│   │   └── system_preferences_page.dart
│   └── profile_and_support/
│       ├── profile_page.dart
│       └── tabs/
│           ├── user_info_tab.dart
│           ├── support_request_tab.dart
│           └── about_us_tab.dart
│
└── widgets/
    ├── common/
    │   ├── custom_button.dart
    │   ├── custom_input_field.dart
    │   ├── custom_card.dart
    │   ├── custom_app_bar.dart
    │   ├── loading_indicator.dart
    │   ├── empty_state_widget.dart
    │   ├── error_state_widget.dart
    │   ├── metric_badge.dart
    │   └── responsive_container.dart
    ├── navigation/
    │   ├── custom_sidebar.dart
    │   └── top_bar.dart
    ├── cards/
    │   ├── power_metric_card.dart
    │   ├── cost_summary_card.dart
    │   ├── metric_summary_card.dart
    │   ├── room_card.dart
    │   ├── device_switch_card.dart
    │   └── top_items_list_card.dart
    ├── charts/
    │   ├── power_gauge_chart.dart
    │   ├── real_time_line_chart.dart
    │   ├── weekly_monthly_bar_chart.dart
    │   ├── consumption_pie_chart.dart
    │   ├── comparison_chart.dart
    │   └── trend_indicator.dart
    ├── dialogs/
    │   ├── alert_popup_dialog.dart
    │   ├── tariff_setting_dialog.dart
    │   ├── date_range_picker.dart
    │   ├── device_control_bottom_sheet.dart
    │   └── export_options_bottom_sheet.dart
    ├── filters/
    │   ├── date_filter_button.dart
    │   ├── filter_chip_group.dart
    │   └── tab_filter.dart
    ├── layouts/
    │   ├── dashboard_grid.dart
    │   ├── main_layout.dart
    │   └── responsive_layout.dart
    └── animations/
        ├── slide_transition.dart
        ├── fade_transition.dart
        └── shimmer_loading.dart
```

---

## 📖 Giải Thích Chi Tiết Từng Phần

### 1. `main.dart`
Điểm khởi chạy ứng dụng. Khởi tạo `MaterialApp`, gắn `theme`, `routes`, và các `BlocProvider` cấp cao nhất (Dashboard, Navigation...) để toàn bộ cây widget bên dưới có thể truy cập state.

---

### 2. `core/` — Cấu Hình Dùng Chung Toàn Hệ Thống

#### 2.1 `core/constants/`
| File | Chức năng |
|---|---|
| `app_colors.dart` | Khai báo toàn bộ bảng màu: Primary (Blue), Warning (Orange/Đỏ khi quá tải), Background, Text (Dark/Gray/Light). Dùng chung để đồng bộ màu sắc toàn app. |
| `app_typography.dart` | Định nghĩa các `TextStyle` chuẩn: heading, subtitle, số liệu lớn (metric), label nhỏ. Giúp giao diện đồng nhất về font-size, font-weight. |
| `app_constants.dart` | Các hằng số cấu hình: padding mặc định, border-radius của card, chiều cao biểu đồ, thời gian animation, ngưỡng công suất mặc định. |
| `app_dimens.dart` | Kích thước layout: độ rộng sidebar, chiều cao top bar, khoảng cách giữa các card, các breakpoint responsive (mobile/tablet/desktop). |
| `enums.dart` | Các kiểu liệt kê dùng chung: `DeviceType` (AC, Fridge, Light...), `AlertType` (OVERLOAD, VOLTAGE_HIGH...), `AlertSeverity` (HIGH/MEDIUM/LOW). |

#### 2.2 `core/theme/`
| File | Chức năng |
|---|---|
| `app_theme.dart` | Gom `light_theme` và `dark_theme` thành `ThemeData` để gắn vào `MaterialApp`. |
| `light_theme.dart` / `dark_theme.dart` | Định nghĩa riêng theme sáng/tối (màu nền, màu chữ, màu AppBar...). |

#### 2.3 `core/utils/`
| File | Chức năng |
|---|---|
| `responsive_helper.dart` | Cung cấp hàm kiểm tra kích thước màn hình: `isMobile()`, `isTablet()`, `isDesktop()` — quyết định layout hiển thị mấy cột. |
| `size_config.dart` | Tính toán kích thước tương đối theo màn hình (giúp UI co giãn đều trên nhiều thiết bị). |
| `electricity_calculator.dart` | Thuật toán tính tiền điện theo bậc thang EVN dựa trên số kWh tiêu thụ. |
| `formatters.dart` | Định dạng hiển thị: tiền VNĐ (`1.500.000 ₫`), công suất (`2.45 kW`), ngày giờ, khoảng thời gian (`15 Sep - 21 Sep`), phần trăm xu hướng (`↑ +5.2%`). |

#### 2.4 `core/extensions/`
| File | Chức năng |
|---|---|
| `string_extension.dart` | Mở rộng `String` (VD: `.capitalize()`). |
| `num_extension.dart` | Mở rộng `num` để format nhanh giá trị số thành tiền/đơn vị. |
| `date_extension.dart` | Mở rộng `DateTime` để format ngày tháng nhanh trong widget. |

---

### 3. `data/` — Tầng Dữ Liệu (Chưa Có Backend)

#### 3.1 `data/models/`
Định nghĩa cấu trúc dữ liệu (object models) ánh xạ với dữ liệu thực tế sau này sẽ lấy từ MQTT/API:

| File | Nội dung chính |
|---|---|
| `room_model.dart` | id, tên phòng, công suất hiện tại, công suất tối đa, danh sách thiết bị. |
| `device_model.dart` | id, tên, loại thiết bị, trạng thái bật/tắt, công suất hiện tại, relay ID. |
| `energy_record_model.dart` | Bản ghi lịch sử: voltage, current, power, energy (kWh), cost, timestamp. |
| `alert_model.dart` | id, loại cảnh báo, mức độ nghiêm trọng, nội dung, trạng thái đã xử lý hay chưa. |
| `user_profile_model.dart` | Thông tin cá nhân: tên, SĐT, email, gói dịch vụ đang dùng, giới hạn thiết bị/phòng. |
| `dashboard_summary_model.dart` | Model tổng hợp cho trang chủ: công suất hiện tại, % sử dụng, điện năng/tiền tháng này, top thiết bị, danh sách cảnh báo. |
| `chart_data_model.dart` | Cấu trúc dữ liệu chung cho các loại biểu đồ (label, value, timestamp...). |

#### 3.2 `data/mock_data/`
Dữ liệu giả lập (hardcode) để dựng và test UI khi chưa có backend/MQTT thật:

| File | Nội dung |
|---|---|
| `mock_rooms.dart` | Danh sách phòng mẫu (Phòng khách, Phòng ngủ, Nhà bếp...) với công suất giả định. |
| `mock_devices.dart` | Danh sách thiết bị mẫu gắn với từng phòng. |
| `mock_energy_records.dart` | Chuỗi dữ liệu điện năng theo thời gian để vẽ biểu đồ. |
| `mock_alerts.dart` | Danh sách cảnh báo mẫu (quá tải, điện áp cao...). |

#### 3.3 `data/repositories/`
Lớp trung gian cung cấp dữ liệu cho BLoC — hiện tại lấy từ `mock_data`, sau này có thể thay bằng gọi MQTT/API mà không cần sửa logic ở tầng trên:

| File | Chức năng |
|---|---|
| `room_repository.dart` | Lấy danh sách phòng, lấy chi tiết 1 phòng, cập nhật thông tin phòng. |
| `device_repository.dart` | Lấy danh sách thiết bị, lấy thiết bị theo phòng, bật/tắt thiết bị, lấy lịch sử hoạt động. |
| `energy_repository.dart` | Lấy dữ liệu điện năng theo khoảng ngày, tổng hợp theo ngày/tuần/tháng, lấy xu hướng nhiều tháng. |
| `alert_repository.dart` | Lấy cảnh báo đang active, lấy toàn bộ lịch sử cảnh báo, đánh dấu đã xử lý. |
| `dashboard_repository.dart` | Gom dữ liệu tổng hợp cho trang Dashboard chính. |

---

### 4. `logic/` — Quản Lý Trạng Thái (BLoC)

Mỗi module gồm 3 file chuẩn: `*_bloc.dart` (xử lý logic), `*_event.dart` (hành động người dùng/hệ thống gửi vào), `*_state.dart` (trạng thái UI phản hồi lại).

| Module | Chức năng chính |
|---|---|
| `dashboard/` | Quản lý state cho trang chủ: load dữ liệu tổng hợp, refresh real-time, đổi khoảng thời gian xem. |
| `energy_monitor/` | Xử lý cập nhật công suất tức thời (real-time), phát dữ liệu mới cho biểu đồ line chart. |
| `report/` | Quản lý filter ngày, loại biểu đồ (tuần/tháng/so sánh 3 tháng), trạng thái xuất báo cáo. |
| `device_control/` | Xử lý bật/tắt thiết bị, hẹn giờ, đồng bộ trạng thái thiết bị lên UI. |
| `alert/` | Nhận, đếm, lọc cảnh báo theo mức độ nghiêm trọng. |
| `navigation/` | Quản lý trang hiện tại đang chọn trên sidebar/bottom nav, dùng để highlight menu active. |
| `settings/` | Quản lý các tuỳ chọn cấu hình: giá điện, ngưỡng cảnh báo, giao diện sáng/tối. |

---

### 5. `routes/` — Điều Hướng

| File | Chức năng |
|---|---|
| `app_routes.dart` | Khai báo tên đường dẫn (route name) dạng hằng số: `/home`, `/report`, `/alerts`... |
| `route_generator.dart` | Hàm `onGenerateRoute` ánh xạ route name → Widget Page tương ứng, hỗ trợ truyền tham số giữa các trang. |

---

### 6. `pages/` — Các Màn Hình Chính

#### 6.1 `home/` (Trang Chủ - Dashboard)
| File | Chức năng |
|---|---|
| `home_page.dart` | Trang chính hiển thị dashboard: các metric card, biểu đồ real-time, danh sách phòng/thiết bị. |
| `home_layout.dart` | Bố cục khung cho Home: desktop hiển thị sidebar cố định, mobile dùng drawer. |
| `dashboard_provider.dart` | Cung cấp dữ liệu dashboard (qua BLoC) xuống các widget con. |
| `room_detail_page.dart` | Trang chi tiết 1 phòng: danh sách thiết bị con, công suất từng thiết bị. |

#### 6.2 `report/` (Báo Cáo & Thống Kê)
| File | Chức năng |
|---|---|
| `report_page.dart` | Trang báo cáo chính: bộ lọc ngày, tab chuyển đổi loại biểu đồ, các chỉ số tổng kết. |
| `report_tab_view.dart` | Xử lý logic chuyển tab (Tuần / Tháng / So sánh 3 tháng). |
| `invoice_export_view.dart` | Xem trước và xuất hóa đơn tiền điện dạng PDF/Excel. |

#### 6.3 `alerts/` (Cảnh Báo)
| File | Chức năng |
|---|---|
| `alerts_page.dart` | Danh sách cảnh báo, có filter theo mức độ nghiêm trọng. |
| `alert_timeline.dart` | Hiển thị cảnh báo dạng timeline dọc theo thời gian. |
| `alert_detail_page.dart` | Trang chi tiết 1 cảnh báo cụ thể. |

#### 6.4 `settings/` (Cài Đặt)
| File | Chức năng |
|---|---|
| `settings_page.dart` | Trang cài đặt tổng, liệt kê các mục cài đặt con. |
| `tariff_settings_page.dart` | Cài đặt giá điện theo bậc thang (EVN/Trọ). |
| `alert_threshold_page.dart` | Cài đặt ngưỡng công suất tối đa để kích hoạt cảnh báo. |
| `system_preferences_page.dart` | Tuỳ chỉnh chung: ngôn ngữ, giao diện sáng/tối. |

#### 6.5 `profile_and_support/` (Hồ Sơ & Hỗ Trợ)
| File | Chức năng |
|---|---|
| `profile_page.dart` | Trang gộp 3 tab: thông tin cá nhân, hỗ trợ, giới thiệu nhóm. |
| `tabs/user_info_tab.dart` | Thông tin cá nhân: SĐT, gói dịch vụ đang dùng. |
| `tabs/support_request_tab.dart` | Form liên hệ, yêu cầu bảo trì/nâng cấp hệ thống. |
| `tabs/about_us_tab.dart` | Giới thiệu nhóm phát triển, phiên bản phần mềm. |

---

### 7. `widgets/` — Thành Phần Giao Diện Tái Sử Dụng

#### 7.1 `widgets/common/` — Widget Dùng Chung
| File | Chức năng |
|---|---|
| `custom_button.dart` | Nút bấm chuẩn hoá style toàn app. |
| `custom_input_field.dart` | Ô nhập liệu chuẩn hoá (label, hint, validator). |
| `custom_card.dart` | Card nền trắng bo góc, có padding/shadow chuẩn — dùng làm khung cho mọi widget khác. |
| `custom_app_bar.dart` | Thanh app bar tái sử dụng cho các trang con. |
| `loading_indicator.dart` | Icon loading khi đang tải dữ liệu. |
| `empty_state_widget.dart` | Hiển thị khi danh sách rỗng (chưa có thiết bị/cảnh báo). |
| `error_state_widget.dart` | Hiển thị khi có lỗi, kèm nút thử lại. |
| `metric_badge.dart` | Nhãn nhỏ hiển thị 1 chỉ số kèm icon. |
| `responsive_container.dart` | Container tự điều chỉnh kích thước theo màn hình. |

#### 7.2 `widgets/navigation/`
| File | Chức năng |
|---|---|
| `custom_sidebar.dart` | Thanh điều hướng dọc bên trái (giống hình dashboard mẫu), có icon + label, highlight trang đang chọn. |
| `top_bar.dart` | Thanh trên cùng: ô tìm kiếm, chuông thông báo, avatar người dùng. |

#### 7.3 `widgets/cards/`
| File | Chức năng |
|---|---|
| `power_metric_card.dart` | Card hiển thị công suất hiện tại dạng gauge (VD: 20.5kW / 30kW). |
| `cost_summary_card.dart` | Card tạm tính tiền điện tháng hiện tại. |
| `metric_summary_card.dart` | Card số liệu tổng quát (icon + số lớn + label + xu hướng) — giống các card "$8,500 Earned this month" trong ảnh mẫu. |
| `room_card.dart` | Card tóm tắt 1 phòng: tên, công suất, số thiết bị. |
| `device_switch_card.dart` | Card thiết bị có nút gạt bật/tắt trực tiếp. |
| `top_items_list_card.dart` | Danh sách xếp hạng (VD: thiết bị tiêu thụ nhiều điện nhất) — giống "Top Deals" trong ảnh mẫu. |

#### 7.4 `widgets/charts/`
| File | Chức năng |
|---|---|
| `power_gauge_chart.dart` | Biểu đồ đồng hồ đo (gauge) hiển thị % công suất đang dùng, đổi màu theo mức độ. |
| `real_time_line_chart.dart` | Biểu đồ đường cập nhật liên tục theo thời gian thực. |
| `weekly_monthly_bar_chart.dart` | Biểu đồ cột so sánh tiêu thụ theo tuần/tháng. |
| `consumption_pie_chart.dart` | Biểu đồ tròn thể hiện tỷ trọng tiêu thụ giữa các thiết bị. |
| `comparison_chart.dart` | Biểu đồ so sánh dữ liệu 3 tháng gần nhất. |
| `trend_indicator.dart` | Icon mũi tên tăng/giảm kèm % xu hướng so với kỳ trước. |

#### 7.5 `widgets/dialogs/`
| File | Chức năng |
|---|---|
| `alert_popup_dialog.dart` | Popup bật lên khi phát hiện sự cố nguy hiểm (quá tải, chập cháy...). |
| `tariff_setting_dialog.dart` | Popup nhập giá điện tùy chỉnh. |
| `date_range_picker.dart` | Chọn khoảng ngày xem báo cáo (giống "15 Sep - 21 Sep 2021" trong ảnh mẫu). |
| `device_control_bottom_sheet.dart` | Bottom sheet điều khiển chi tiết 1 thiết bị (bật/tắt, hẹn giờ, lịch sử). |
| `export_options_bottom_sheet.dart` | Bottom sheet chọn định dạng xuất báo cáo (PDF/Excel/CSV). |

#### 7.6 `widgets/filters/`
| File | Chức năng |
|---|---|
| `date_filter_button.dart` | Nút chọn nhanh khoảng thời gian hiển thị trên trang Report. |
| `filter_chip_group.dart` | Nhóm chip lọc (VD: lọc cảnh báo theo mức độ). |
| `tab_filter.dart` | Thanh tab chuyển đổi giữa các chế độ xem (Tuần/Tháng/So sánh). |

#### 7.7 `widgets/layouts/`
| File | Chức năng |
|---|---|
| `dashboard_grid.dart` | Bố cục dạng lưới responsive cho các card trên Dashboard (1/2/3 cột tuỳ màn hình) — cốt lõi để tạo layout giống ảnh mẫu. |
| `main_layout.dart` | Khung sườn chung: Sidebar trái + TopBar trên + nội dung chính. |
| `responsive_layout.dart` | Widget helper chuyển đổi layout theo kích thước màn hình (mobile/tablet/desktop). |

#### 7.8 `widgets/animations/`
| File | Chức năng |
|---|---|
| `slide_transition.dart` | Hiệu ứng trượt khi chuyển trang/mở panel. |
| `fade_transition.dart` | Hiệu ứng mờ dần khi hiển thị nội dung mới. |
| `shimmer_loading.dart` | Hiệu ứng loading dạng skeleton (khung xám nhấp nháy) khi đang tải dữ liệu. |

---

## 🗺️ Luồng Hoạt Động Tổng Quát

```
User mở app
   │
   ▼
main.dart khởi tạo Theme + Routes + BlocProviders
   │
   ▼
NavigationBloc xác định trang hiện tại → route_generator điều hướng tới Page tương ứng
   │
   ▼
Page gọi Bloc tương ứng (VD: HomePage → DashboardBloc)
   │
   ▼
Bloc gọi Repository (VD: DashboardRepository)
   │
   ▼
Repository lấy dữ liệu từ mock_data (giai đoạn frontend-only)
   │
   ▼
Bloc emit State mới → Page rebuild UI
   │
   ▼
UI hiển thị qua các widget tái sử dụng (cards, charts, layouts...)
```

---

## ✅ Thứ Tự Xây Dựng Đề Xuất

1. **`core/`** — màu sắc, typography, constants, extensions
2. **`data/models/` + `data/mock_data/`** — định nghĩa dữ liệu giả lập
3. **`data/repositories/`** — lớp cung cấp dữ liệu mock
4. **`logic/`** — các BLoC xử lý state
5. **`widgets/common/` + `widgets/layouts/`** — nền tảng UI dùng chung
6. **`widgets/cards/` + `widgets/charts/`** — thành phần hiển thị dữ liệu
7. **`widgets/navigation/` + `widgets/dialogs/` + `widgets/filters/`** — tương tác
8. **`pages/`** — ráp các trang hoàn chỉnh
9. **`routes/`** — nối điều hướng giữa các trang
10. **`widgets/animations/`** — hoàn thiện trải nghiệm (làm sau cùng)
