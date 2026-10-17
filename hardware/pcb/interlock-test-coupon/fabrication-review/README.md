# 仅供测试板制造审核的输出

文件由当前 KiCad 板文件实际导出：双层铜、阻焊、顶层焊膏/丝印、板框与 Excellon 钻孔。板框约66×41mm，当前板厚配置1.6mm。它不是H1眼镜主板，没有进行工厂DFM、封装实测或电气故障注入。

下单前独立核对TPS22918 DBV和MCP6547 DIP8封装/引脚、LED封装极性、连接器、铜厚、最小线距/孔径和阻焊桥；清除或解释全部库元数据警告。先限流、离体测试。相机IO隔离和LED被遮挡检测未实现，不能把这块板当作通过验收的隐私保护产品。

重导出示例（KiCad 7）：

```bash
kicad-cli pcb export gerbers --layers F.Cu,B.Cu,F.Paste,F.Silkscreen,F.Mask,B.Mask,Edge.Cuts --output hardware/pcb/interlock-test-coupon/fabrication-review/ hardware/pcb/interlock-test-coupon/interlock-test.kicad_pcb
kicad-cli pcb export drill --format excellon --excellon-units mm --generate-map --map-format svg --output hardware/pcb/interlock-test-coupon/fabrication-review/ hardware/pcb/interlock-test-coupon/interlock-test.kicad_pcb
python scripts/check_interlock.py
```
