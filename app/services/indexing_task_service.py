"""索引任务应用服务。"""

from loguru import logger

from app.persistence import indexing_task_repository
from app.services.vector_index_service import vector_index_service


class IndexingTaskService:
    """管理索引任务的提交与执行。"""

    def submit_task(self, filename: str, file_path: str) -> str:
        """登记待执行的索引任务。"""
        task_id = indexing_task_repository.create_task(filename, file_path)
        logger.info(f"已提交索引任务: {task_id}, 文件: {file_path}")
        return task_id

    def process_task(self, task_id: str, file_path: str) -> None:
        """执行索引任务并更新状态。"""
        try:
            indexing_task_repository.update_task(task_id, status="processing")
            vector_index_service.index_single_file(file_path)
            indexing_task_repository.update_task(task_id, status="completed")
            logger.info(f"索引任务执行完成: {task_id}")
        except Exception as exc:
            indexing_task_repository.update_task(
                task_id,
                status="failed",
                error_message=str(exc),
            )
            logger.error(f"索引任务执行失败: {task_id}, 错误: {exc}")


indexing_task_service = IndexingTaskService()
