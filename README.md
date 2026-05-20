# Backgroud
這個專案是基於國立臺灣大學的課程「Practical Applications of Environmental Big Data」的小組期末專案報告。專案發想來源為：Bountos, Nikolaos Ioannis, Maria Sdraka, Angelos Zavras, et al. “Kuro Siwo: 33 Billion $m^2$ under the Water. A Global Multi-Temporal Satellite Dataset for Rapid Flood Mapping.” Advances in Neural Information Processing Systems 37, 2024, 38105–21. https://doi.org/10.52202/079017-1204.

# Objective
以Kuro Siwo 資料集為基礎，加入同樣與淹水有關之地理資料，
並將原始資料轉化為高效、可搜索且具備機器可讀性的擴充資料
集，以支援下游的淹水環境分析與淹水辨識模型

# End-to-End Workflow
1. Event-based Filtering
    1. 下載 Kuro Siwo 43個淹水事件資料集
    2. 使用 datetime 從檔名取得時間，使用 geopandas 從檔案取得四邊界座標 [kurosiwo_data.ipynb]
2. Web crawlers & Basic Data CSV
    1. 使用網路爬蟲在EMSR網站抓取各淹水事件ID所對應的事件名稱、國家
    2. 將當前資料彙整為一完整的CSV檔案，作為後續 STAC 建置之基礎
3. Preprocessing & Download
    1. 從 GEE 下載目標空間範圍及目標時間的資料 [S2_data.ipynb] [IMERG_catch.ipynb]
    2. 進行累加與合成等運算
    3. 利用GEE平台已有之Lazy evaluation, 平行運算, chunking之機制來輸出
4. Extract Kuro Siwo files
    1. 對 Kuro Siwo 碎塊資料進行合併，並整理至各事件資料夾 [extract_kurosiwo.ipynb]
5. Data Engineering – COG strategy [strategy.ipynb]
    1. 輸出 Cloud-Optimized GeoTIFF 格式
    2. 選定某幾個事件以不同 tiling 策略進行效能比較
    3. 分析結果並決定最合適的策略
6. STAC Catalog
    1. 抽取檔案、名稱轉換，建構 STAC 及其所需 metadata [Final_Stac.py]
7. WebGIS
    1. 讀取 STAC ，以 Leaflet 建構網頁前端畫面與功能

# Project Environment Using
CPU: AMD Ryzen 9 5950X 16-Core Processor (Threads per core: 2).
RAM: 78GB
Disk: NAS storage - 84 TB
OS: Linux (Ubuntu)
Dependency Management: uv

# Dataset
| | Sentinel-1 SAR GRD | Sentinel-2 MSI L2A | IMERG | Dynamic World V1 | SRTM | Flood event labeled data | Manual labeled data |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Characteristic** | Synthetic Aperture Radar | Multi-spectral imaging for land monitoring | Global Precipitation Measurement | Near real-time global land cover / land use classification | Digital Elevation Models (DEMs) | Labeled data | Labeled data |
| **Spatial Resolution** | 10 m | 10 m | 11132 m | 10 m | 10 m | (.shp) | 10 m |
| **Time Resolution** | 6 Days | 5 Days | 30 Minutes | 5 Days | -- | -- | -- |
| **Selected Variables** | VV, VH | B4 (Red), B3 (Green), B2 (Blue), B8 (NIR) | precipitation | water, trees, grass, flooded_vegetation, crops, shrub_and_scrub, built, bare, snow_and_ice | elevation | flooded area | 0 (permanent water)<br>1 (no water)<br>2 (water)<br>3 (flood) |
| **Source** | Kuro Siwo dataset | GEE | GEE | GEE | Kuro Siwo dataset | Kuro Siwo dataset | Kuro Siwo dataset |
| **Preprocess work we did** | Merge the files to one file | Mosaic stitching images from three days prior and later | Sum the results of the previous 7 days | Year-scale composite time window;<br>Generate both probabilistic and categorical products | Merge the files to one file | -- | Merge the files to one file |