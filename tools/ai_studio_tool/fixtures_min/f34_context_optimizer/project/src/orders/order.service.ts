import { calculatePricing } from './pricing';
import { orderRepository } from './repository';
export const createOrder = (id: string, quantity: number) => {
  orderRepository.set(id, calculatePricing(quantity));
};
