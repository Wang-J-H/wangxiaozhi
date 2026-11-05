"""
Xiaozhi - 本地 Qwen 模型供应商初始化脚本
在首次启动后运行，自动添加本地 vLLM Qwen 模型供应商
"""
import asyncio
import os
import sys

# 添加包路径
sys.path.insert(0, '/app/package')

async def seed_local_qwen():
    # 延迟等待服务完全启动
    await asyncio.sleep(5)
    
    from sqlalchemy import text
    from xiaozhi.services.model_provider import ModelProviderService
    from xiaozhi.storage.database import get_async_session
    
    # 本地 Qwen 地址（通过 host.docker.internal 访问宿主机 vLLM）
    qwen_url = os.environ.get('XIAOZHI_LOCAL_QWEN_URL', 'http://host.docker.internal:8000/v1')
    
    async with get_async_session() as session:
        service = ModelProviderService(session)
        
        # 检查是否已存在
        existing = await service.get_by_provider_id('local-qwen')
        if existing:
            print("✅ 本地 Qwen 模型供应商已存在，跳过")
            return
        
        # 创建模型供应商
        provider = await service.create_provider({
            'provider_id': 'local-qwen',
            'provider_name': '本地 Qwen (vLLM)',
            'base_url': qwen_url,
            'models': [
                {
                    'model_id': 'Qwen/Qwen2.5-72B-Instruct',
                    'model_type': 'chat',
                    'enabled': True,
                }
            ],
            'enabled': True,
        })
        print(f"✅ 已添加本地 Qwen 模型供应商 (provider_id: local-qwen)")
        print(f"   接口地址: {qwen_url}")
        print(f"   模型: Qwen/Qwen2.5-72B-Instruct")

if __name__ == '__main__':
    print("=" * 50)
    print("Xiaozhi - 本地 Qwen 模型初始化")
    print("=" * 50)
    asyncio.run(seed_local_qwen())
    print("\n完成！请在 Web 界面「智能体管理 → 模型供应商」中查看。")
