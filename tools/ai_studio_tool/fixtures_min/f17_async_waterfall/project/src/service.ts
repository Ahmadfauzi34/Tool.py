import { Injectable } from '@angular/core';

@Injectable()
export class DataService {
  async loadData() {
    const users = await this.fetchUsers();
    const orders = await this.fetchOrders();
    const config = await this.fetchConfig();
    return { users, orders, config };
  }

  async processItems(ids: string[]) {
    for (const id of ids) {
      const item = await this.fetchItem(id);
      console.log(item);
    }
  }
}
