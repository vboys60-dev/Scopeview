# 儀器搜尋只用 VISA 列表與 mDNS，不掃網段

VISA 的 `list_resources()` 只看得到 USB 與序列埠，LAN 上的示波器不會出現（實測本機只掃到兩個序列埠）。要讓網路上的儀器自己冒出來，選項是 mDNS/LXI 廣播查詢或逐一探測網段的 5025 port。我們用 zeroconf 查 `_hislip._tcp` / `_lxi._tcp` / `_scpi-raw._tcp`，並保留手動輸入 IP 作為後路；明確拒絕掃網段，因為它慢，而且在企業網路上會被資安設備判定為連接埠掃描。
