export interface UserDTO {
  id: string;
  name: string;
  email: string;
}

export interface UserViewModel {
  id: string;
  name: string;
  email: string;
}

export interface Product {
  sku: string;
  price: number;
}

export type ProductAlias = {
  sku: string;
  price: number;
};

export interface Order {
  orderId: string;
  total: number;
  createdAt: string;
}
