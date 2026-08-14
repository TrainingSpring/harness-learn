# 基础Tool的实现

从这里开始，我们参考一些[pi-agent](https://github.com/earendil-works/pi)的实现方式

## 什么是PI-Agent
PI是*Mario Zechner*开源的一个极简的Agent框架 ， 用Typescript编写， 也是小龙虾（OpenClaw）的核心框架。 


# 核心tool

> 在Pi中， 仅仅只内置了4个工具： read , write , edit , bash。 
> 这几项基本能涵盖日常的任务需求了。有其他tool的时候，再新增即可。 
> read 读取能力
> write 写入能力
> edit  编辑能力
> bash  终端命令能力