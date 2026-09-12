import { setupServer } from "msw/node";

/** 单元测试共享的 API 模拟服务；具体场景由各测试按需注册 handler。 */
export const server = setupServer();
