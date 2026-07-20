# 1. 初始化
git init

# 2. 添加所有文件
git add .

# 3. 提交
git commit -m "首次提交"

# 4. 查看当前分支
git branch
# 如果显示 master，用下面的命令推送
# 如果显示 main，用下面的命令推送

# 5. 推送到 GitHub（根据分支名选择一条）
git push -u origin master   # 如果分支是 master
# 或
git push -u origin main     # 如果分支是 main

# 查看修改了哪些文件
git status

# 添加所有修改的文件
git add .

# 提交修改
git commit -m "描述你修改了什么，比如：修复K线图显示问题"

# 推送到 GitHub
git push