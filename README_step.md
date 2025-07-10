# T4T 用户手册

欢迎使用 T4T (Task for T)，一款专为开发者设计的智能任务执行工具。本手册将引导您完成安装、熟悉界面、管理任务，并进行个性化设置。

## 1. 安装指南

T4T 的安装过程非常简单。请按照以下步骤操作：

1. **克隆代码库**:

    ```bash
    git clone https://github.com/your-repo/T4T.git
    cd T4T
    ```

2. **安装依赖**:
    我们建议使用虚拟环境来管理项目依赖。

    ```bash
    python -m venv venv
    source venv/bin/activate  # macOS/Linux
    # venv\Scripts\activate  # Windows

    pip install -r requirements.txt
    ```

3. **运行应用**:

    ```bash
    python main.py
    ```

    应用启动后，您将看到主界面。

## 2. 界面说明

T4T 的主界面分为几个核心区域：

- **任务列表 (左侧)**: 显示所有已创建的任务。您可以选择、新建或删除任务。
- **任务详情区 (右侧)**: 当选中一个任务时，这里会显示任务的配置、输出和历史记录。
- **主菜单栏**: 提供访问设置、主题和语言选项的入口。
- **状态栏**: 显示当前应用的状态和重要通知。

## 3. 任务管理

任务是 T4T 的核心功能。每个任务都包含独立的配置和执行逻辑。

### 创建新任务

1. 点击左侧任务列表下方的“新建任务”按钮。
2. 在弹出的对话框中，输入任务名称和描述。
3. 配置任务的执行脚本和相关参数。

### 导入示例任务

为了帮助您快速上手，我们提供了一些预设的示例任务。

1. 进入 `tasks/` 目录。
2. 复制一个示例任务目录（例如 `sample_task`）到您的工作区。
3. 在 T4T 应用中，点击“刷新任务列表”，新任务即会显示。

### 示例任务：网页内容抓取

这是一个简单的示例，用于演示如何使用 T4T 抓取并保存网页标题。

**任务配置 (`config.json`)**:

```json
{
  "url": "https://docs.cline.bot",
  "output_file": "web_title.txt"
}
```

**执行脚本 (`main.py`)**:

```python
import requests
from bs4 import BeautifulSoup
import json

def run_task():
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    url = config.get("url")
    output_file = config.get("output_file")

    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.title.string

        with open(output_file, 'w') as f:
            f.write(title)
        
        print(f"成功抓取网页标题并保存到 {output_file}")

    except Exception as e:
        print(f"任务执行失败: {e}")

if __name__ == "__main__":
    run_task()
```

## 4. 主题和语言设置

### 切换主题

T4T 支持浅色和深色两种主题。

1. 前往 `设置` -> `主题`。
2. 选择 `light` 或 `dark` 主题。
3. 应用界面将立即更新。

### 更改语言

您可以根据偏好切换界面语言。

1. 前往 `设置` -> `语言`。
2. 选择您希望使用的语言（例如 `English`, `简体中文`）。
3. 重启应用后，语言设置将生效。

---

感谢您使用 T4T！如果您有任何问题或建议，请通过我们的社区渠道联系我们
