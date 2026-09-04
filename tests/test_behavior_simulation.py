"""
CI 环境人类行为模拟功能验证脚本

用于测试新增的行为模拟功能是否正常工作。
"""

import asyncio
import os
import sys

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.ci_config import CIConfig
from utils.logger import setup_logger

logger = setup_logger(__name__)


def test_ci_config():
    """测试 CI 配置功能"""
    logger.info("=" * 60)
    logger.info("测试 CI 配置功能")
    logger.info("=" * 60)

    # 测试 CI 环境检测
    is_ci = CIConfig.is_ci_environment()
    logger.info(f"当前是否为 CI 环境: {is_ci}")

    # 测试行为模拟开关
    should_simulate = CIConfig.should_enable_behavior_simulation()
    logger.info(f"是否启用行为模拟: {should_simulate}")

    # 测试行为模拟强度
    intensity = CIConfig.get_behavior_simulation_intensity()
    logger.info(f"行为模拟强度: {intensity}")

    # 测试其他 CI 配置
    retry_count = CIConfig.get_retry_count()
    logger.info(f"重试次数: {retry_count}")

    timeout_multiplier = CIConfig.get_ci_timeout_multiplier()
    logger.info(f"超时倍增器: {timeout_multiplier}")

    extended_wait = CIConfig.should_use_extended_wait()
    logger.info(f"是否使用延长等待: {extended_wait}")

    logger.info("")


async def test_human_behavior_import():
    """测试行为模拟模块导入"""
    logger.info("=" * 60)
    logger.info("测试行为模拟模块导入")
    logger.info("=" * 60)

    try:
        from utils.human_behavior import (
            add_random_mouse_jitter,
            simulate_click_with_behavior,
            simulate_form_filling,
            simulate_human_behavior,
            simulate_mouse_movement_to_element,
            simulate_page_interaction,
            simulate_reading_delay,
            simulate_typing,
        )

        imported_functions = (
            simulate_human_behavior,
            simulate_page_interaction,
            simulate_typing,
            simulate_click_with_behavior,
            simulate_reading_delay,
            simulate_mouse_movement_to_element,
            simulate_form_filling,
            add_random_mouse_jitter,
        )
        assert all(callable(function) for function in imported_functions)

        logger.info("✅ 所有函数导入成功:")
        logger.info("   - simulate_human_behavior")
        logger.info("   - simulate_page_interaction")
        logger.info("   - simulate_typing")
        logger.info("   - simulate_click_with_behavior")
        logger.info("   - simulate_reading_delay")
        logger.info("   - simulate_mouse_movement_to_element")
        logger.info("   - simulate_form_filling")
        logger.info("   - add_random_mouse_jitter")

        logger.info("")
        return None

    except ImportError as e:
        logger.error(f"❌ 导入失败: {e}")
        logger.info("")
        raise


def test_authenticator_integration():
    """测试 Authenticator 基类集成"""
    logger.info("=" * 60)
    logger.info("测试 Authenticator 基类集成")
    logger.info("=" * 60)

    try:
        import inspect

        from utils.auth.base import Authenticator

        # 检查基类是否有新增的方法
        methods_to_check = [
            '_simulate_human_click',
            '_simulate_human_typing',
            '_goto_with_behavior',
        ]

        logger.info("检查 Authenticator 基类新增方法:")
        all_methods_exist = True

        for method_name in methods_to_check:
            if hasattr(Authenticator, method_name):
                logger.info(f"   ✅ {method_name} 存在")
            else:
                logger.error(f"   ❌ {method_name} 不存在")
                all_methods_exist = False

        # 检查 __init__ 是否有新增的属性
        logger.info("")
        logger.info("检查 Authenticator 初始化签名:")
        init_signature = inspect.signature(Authenticator.__init__)
        logger.info(f"   参数: {list(init_signature.parameters.keys())}")

        logger.info("")
        assert all_methods_exist

    except Exception as e:
        logger.error(f"❌ 集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        logger.info("")
        raise


def test_environment_variables():
    """测试环境变量配置"""
    logger.info("=" * 60)
    logger.info("测试环境变量配置")
    logger.info("=" * 60)

    env_vars = [
        "CI",
        "GITHUB_ACTIONS",
        "CI_ENABLE_BEHAVIOR_SIMULATION",
        "CI_BEHAVIOR_INTENSITY",
        "CI_RETRY_COUNT",
        "CI_TIMEOUT_MULTIPLIER",
        "CI_EXTENDED_WAIT",
    ]

    logger.info("当前环境变量设置:")
    for var in env_vars:
        value = os.getenv(var, "<未设置>")
        logger.info(f"   {var}: {value}")

    logger.info("")
    logger.info("模拟测试环境变量:")

    # 模拟启用 CI 环境
    os.environ["CI"] = "true"
    os.environ["CI_ENABLE_BEHAVIOR_SIMULATION"] = "true"
    os.environ["CI_BEHAVIOR_INTENSITY"] = "medium"

    logger.info("   设置 CI=true")
    logger.info("   设置 CI_ENABLE_BEHAVIOR_SIMULATION=true")
    logger.info("   设置 CI_BEHAVIOR_INTENSITY=medium")

    is_ci = CIConfig.is_ci_environment()
    should_simulate = CIConfig.should_enable_behavior_simulation()
    intensity = CIConfig.get_behavior_simulation_intensity()

    logger.info("")
    logger.info("验证配置读取:")
    logger.info(f"   is_ci_environment(): {is_ci}")
    logger.info(f"   should_enable_behavior_simulation(): {should_simulate}")
    logger.info(f"   get_behavior_simulation_intensity(): {intensity}")

    success = is_ci and should_simulate and intensity == "medium"
    if success:
        logger.info("   ✅ 环境变量配置正确")
    else:
        logger.error("   ❌ 环境变量配置异常")

    # 恢复环境变量
    for var in ["CI", "CI_ENABLE_BEHAVIOR_SIMULATION", "CI_BEHAVIOR_INTENSITY"]:
        if var in os.environ:
            del os.environ[var]

    logger.info("")
    assert success


def main():
    """运行所有测试"""
    logger.info("")
    logger.info("🚀 开始验证 CI 环境人类行为模拟功能")
    logger.info("")

    results = {}
    try:
        test_ci_config()
        results["CI 配置功能"] = True
        asyncio.run(test_human_behavior_import())
        results["行为模拟模块导入"] = True
        test_authenticator_integration()
        results["Authenticator 集成"] = True
        test_environment_variables()
        results["环境变量配置"] = True
    except Exception:
        # 具体失败已由各测试函数记录。
        results.setdefault("测试执行", False)

    # 汇总结果
    logger.info("=" * 60)
    logger.info("测试结果汇总")
    logger.info("=" * 60)

    all_passed = True
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{test_name}: {status}")
        if not result:
            all_passed = False

    logger.info("")
    if all_passed:
        logger.info("🎉 所有测试通过！功能集成成功！")
        return 0
    else:
        logger.error("⚠️ 部分测试失败，请检查上述错误信息")
        return 1


if __name__ == "__main__":
    sys.exit(main())
