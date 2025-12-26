# prompts.html中 history功能fix

当前的history功能存在以下问题：
1. 每个prompt之间没有隔离，导致一个prompt的history会影响到其他prompt的history


期望的正常逻辑：
1. 每个Agent有自己的history,互不干扰
2. 当编辑后进行版本变动，但是用户只有对prompts变动了才能save changes，否则不允许进行save
3. 其他可自由发挥和排查，要求就是按照企业标准来，这是一个标准的开源仓库