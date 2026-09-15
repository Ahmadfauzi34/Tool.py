import {PLATFORM_ID} from '@angular/core';
import {TestBed} from '@angular/core/testing';
import {App} from './app';

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  it('does not call browser APIs while rendering on the server', async () => {
    TestBed.resetTestingModule();
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [{provide: PLATFORM_ID, useValue: 'server'}],
    }).compileComponents();
    const fetchSpy = vi.spyOn(globalThis, 'fetch');

    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(fixture.componentInstance.loading()).toBe(false);
  });
});
