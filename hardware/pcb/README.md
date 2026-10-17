# PCB交付范围

仅提供原创3.3V LED窗口联锁测试coupon的KiCad源文件、网络连接CSV及可再生脚本；它不是H1整机主板。H1的电源、光机、RF、充电、存储、音频、FPC尚未整合为可投板资料。

测试板有18个器件位、10个网络，已做KiCad复读和DRC。完整结果以`docs/evidence/interlock-drc.txt`为准；元数据警告未隐去。生成脚本依赖KiCad7的pcbnew，运行后须导出网表并与实际板文件连接表核对。封装是自绘嵌入数据，仍需按选定器件独立核图，不能把DRC当作封装、电气或安全功能认证。

制造输出如位于`interlock-test-coupon/fabrication-review/`，只对应这个实验coupon，需工程师审核后才可作为离体测试板打样。没有H1主板Gerber、钢网、飞针测试或整机制造通过声明。

测试板逐件BOM位于`../bom/interlock-coupon.csv`，其MCP6547为DIP8的-I/P版本；SOIC的-I/SN不能焊到当前板。LED具体SKU/极性仍须独立核对。
